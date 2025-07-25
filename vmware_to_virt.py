import os
import sys
import click
import subprocess
import xml.etree.ElementTree as ET
from defusedxml.ElementTree import fromstring
import shutil
from pathlib import Path
import logging

class VMwareToVirtConverter:
    def __init__(self, input_dir, output_dir):
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.vm_name = None
        self.disk_files = []
        
    def validate_input(self):
        """Validate the input directory contains VMware VM files"""
        if not self.input_dir.exists():
            raise FileNotFoundError(f"Input directory '{self.input_dir}' does not exist")
            
        if not self.input_dir.is_dir():
            raise NotADirectoryError(f"Input path '{self.input_dir}' is not a directory")
            
        # Check for at least one .vmx file
        vmx_files = list(self.input_dir.glob("*.vmx"))
        if not vmx_files:
            raise FileNotFoundError(f"No VMware configuration (.vmx) file found in '{self.input_dir}'\n"
                                  f"Please ensure you're pointing to a VMware VM directory")
            
        # Get VM name from .vmx file
        self.vm_name = vmx_files[0].stem
        click.echo(f"Found VMware VM: {self.vm_name}")
        
    def identify_disk_structure(self):
        """Identify VMware disk structure (split vs single disk)"""
        vmdk_files = list(self.input_dir.glob("*.vmdk"))
        
        if not vmdk_files:
            raise FileNotFoundError(f"No VMware disk (.vmdk) files found in '{self.input_dir}'")
        
        # Separate descriptor files from data files
        descriptor_files = []
        data_files = []
        
        for vmdk in vmdk_files:
            # Read first few lines to determine if it's a descriptor or data file
            try:
                with open(vmdk, 'rb') as f:
                    header = f.read(512).decode('utf-8', errors='ignore')
                    
                # Descriptor files contain text configuration
                if 'createType' in header or 'parentFileNameHint' in header:
                    descriptor_files.append(vmdk)
                else:
                    # This is likely a flat/data file
                    data_files.append(vmdk)
            except Exception:
                # If we can't read it, assume it's a data file
                data_files.append(vmdk)
        
        return descriptor_files, data_files
    
    def get_disk_conversion_targets(self):
        """Get the correct VMDK files to convert based on disk structure"""
        descriptor_files, data_files = self.identify_disk_structure()
        
        conversion_targets = []
        
        if descriptor_files:
            # We have descriptor files - use them for conversion
            # qemu-img can handle split disks via descriptor files
            for desc in descriptor_files:
                # Skip snapshot descriptors (contain 'parentFileNameHint')
                try:
                    with open(desc, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        if 'parentFileNameHint' not in content:
                            conversion_targets.append(desc)
                            click.echo(f"Found disk descriptor: {desc.name}")
                        else:
                            click.echo(f"Skipping snapshot descriptor: {desc.name}")
                except Exception as e:
                    click.echo(f"Warning: Could not read {desc.name}: {e}")
        else:
            # No descriptor files found - likely single monolithic disks
            conversion_targets = data_files
            click.echo(f"Found {len(data_files)} monolithic disk file(s)")
        
        if not conversion_targets:
            raise FileNotFoundError("No valid VMDK files found for conversion")
            
        return conversion_targets
    
    def validate_vmware_vm(self):
        """Validate that the VMware VM is suitable for conversion"""
        click.echo("\n🔍 Validating VMware VM...")
        
        validation_errors = []
        warnings = []
        
        # Check for suspended/crashed VM state
        vmem_files = list(self.input_dir.glob("*.vmem"))
        vmss_files = list(self.input_dir.glob("*.vmss"))
        
        if vmem_files:
            warnings.append(f"Found {len(vmem_files)} memory dump files (.vmem) - VM may have been suspended or crashed")
        
        if vmss_files:
            warnings.append(f"Found {len(vmss_files)} snapshot files (.vmss) - VM may be in suspended state")
        
        # Check each VMDK file for bootability
        vmdk_files = list(self.input_dir.glob("*.vmdk"))
        bootable_disks = 0
        
        for vmdk in vmdk_files:
            click.echo(f"  Checking {vmdk.name}...")
            
            # Check if VMDK has a partition table
            try:
                result = subprocess.run([
                    "fdisk", "-l", str(vmdk)
                ], capture_output=True, text=True, check=False)
                
                if "Disklabel type:" in result.stdout or "Device" in result.stdout:
                    click.echo(f"    ✅ {vmdk.name} has valid partition table")
                    bootable_disks += 1
                else:
                    click.echo(f"    ❌ {vmdk.name} has no partition table")
                    
                    # Check if it's a descriptor file (split disk)
                    try:
                        with open(vmdk, 'r', encoding='utf-8') as f:
                            content = f.read(1024)  # Read first 1KB
                            if "createType" in content and "VMDK" in content:
                                click.echo(f"    ℹ️  {vmdk.name} appears to be a descriptor file (split disk)")
                                continue  # Skip validation for descriptor files
                    except:
                        pass
                    
                    validation_errors.append(f"{vmdk.name} has no partition table and may not be bootable")
                        
            except Exception as e:
                warnings.append(f"Could not analyze {vmdk.name}: {e}")
        
        # Check for boot sector signatures
        for vmdk in vmdk_files:
            if vmdk.stat().st_size < 1024:  # Skip very small files
                continue
                
            try:
                result = subprocess.run([
                    "file", "-s", str(vmdk)
                ], capture_output=True, text=True, check=False)
                
                if "boot sector" in result.stdout.lower() or "filesystem" in result.stdout.lower():
                    click.echo(f"    ✅ {vmdk.name} has recognizable boot/filesystem signature")
                elif "data" == result.stdout.strip().split(": ")[1]:
                    warnings.append(f"{vmdk.name} shows as 'data' with no recognizable structure")
                    
            except Exception as e:
                warnings.append(f"Could not check boot signature for {vmdk.name}: {e}")
        
        # Display warnings
        if warnings:
            click.echo("\n⚠️  Warnings detected:")
            for warning in warnings:
                click.echo(f"    • {warning}")
        
        # Check for critical errors
        if validation_errors:
            click.echo("\n❌ Critical validation errors:")
            for error in validation_errors:
                click.echo(f"    • {error}")
            
            click.echo("\n🛑 VM validation failed!")
            click.echo("\nThis VMware VM appears to be corrupted or non-bootable.")
            click.echo("Possible causes:")
            click.echo("  • VM was not properly shut down")
            click.echo("  • VM is in suspended/snapshot state")
            click.echo("  • Disk corruption occurred")
            click.echo("  • VM was never bootable to begin with")
            click.echo("\nRecommendations:")
            click.echo("  • Boot the VM in VMware first to verify it works")
            click.echo("  • Properly shut down the VM before conversion")
            click.echo("  • Delete any snapshots and memory files")
            click.echo("  • Use VMware's disk repair tools if needed")
            
            return False
        
        if bootable_disks == 0 and not warnings:
            click.echo("\n⚠️  No bootable disks detected, but no critical errors found.")
            click.echo("Conversion will proceed, but resulting VM may not boot.")
        
        click.echo("\n✅ VM validation passed - proceeding with conversion")
        return True
    
    def convert_disk_images(self):
        """Convert VMDK files to QCOW2 format"""
        click.echo("\n🔄 Converting disk images...")
        
        # Check if qemu-img is available
        try:
            subprocess.run(["qemu-img", "--version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError("qemu-img not found. Please install qemu-utils package:\n"
                             "  Ubuntu/Debian: sudo apt-get install qemu-utils\n"
                             "  CentOS/RHEL: sudo yum install qemu-img\n"
                             "  Fedora: sudo dnf install qemu-img")
        
        # Get the correct files to convert
        conversion_targets = self.get_disk_conversion_targets()
        
        click.echo(f"Converting {len(conversion_targets)} disk image(s)...")
        
        for i, vmdk in enumerate(conversion_targets, 1):
            output_path = self.output_dir / f"{vmdk.stem}.qcow2"
            
            click.echo(f"  [{i}/{len(conversion_targets)}] Converting {vmdk.name} -> {output_path.name}")
            
            try:
                # Detect the actual format of the VMDK file
                format_result = subprocess.run([
                    "qemu-img", "info", "--output=json", str(vmdk)
                ], capture_output=True, text=True, check=True)
                
                import json
                info = json.loads(format_result.stdout)
                detected_format = info.get('format', 'vmdk')
                
                click.echo(f"    Detected format: {detected_format}")
                
                # For raw format VMDKs, we need to be more careful about preserving boot sectors
                if detected_format == 'raw':
                    click.echo(f"    Raw format detected - using special conversion to preserve boot sector")
                    
                    # First, try to convert as vmdk format to preserve structure
                    try:
                        result = subprocess.run([
                            "qemu-img", "convert", "-f", "vmdk",
                            "-O", "qcow2", "-p",
                            str(vmdk),
                            str(output_path)
                        ], capture_output=True, text=True, check=True)
                        click.echo(f"    ✅ Successfully converted as VMDK format (preserving structure)")
                    except subprocess.CalledProcessError:
                        # If VMDK format fails, fall back to raw format
                        click.echo(f"    VMDK format failed, using raw format conversion")
                        click.echo(f"    Converting {vmdk.stat().st_size // (1024**3):.1f}GB disk - this should take 5-15 minutes...")
                        result = subprocess.run([
                            "qemu-img", "convert", "-f", "raw",
                            "-O", "qcow2", "-p",
                            str(vmdk),
                            str(output_path)
                        ], text=True, check=True)  # Remove capture_output to show progress
                        
                        if result.stderr:
                            click.echo(f"    Warning: {result.stderr}")
                else:
                    # Use detected format for non-raw formats
                    result = subprocess.run([
                        "qemu-img", "convert", "-f", detected_format,
                        "-O", "qcow2", "-p",
                        str(vmdk),
                        str(output_path)
                    ], capture_output=True, text=True, check=True)
                
                # Verify the converted disk has a valid partition table
                self.verify_converted_disk(output_path)
                
                self.disk_files.append(output_path)
                click.echo(f"    ✅ Successfully converted {vmdk.name}")
                
            except subprocess.CalledProcessError as e:
                error_msg = e.stderr if e.stderr else str(e)
                raise RuntimeError(f"Failed to convert {vmdk.name}: {error_msg}")
    
    def verify_converted_disk(self, disk_path):
        """Verify that the converted disk has a valid partition table"""
        try:
            # Check if the disk has a valid partition table
            result = subprocess.run([
                "fdisk", "-l", str(disk_path)
            ], capture_output=True, text=True, check=False)
            
            if "Disklabel type:" in result.stdout or "Device" in result.stdout:
                click.echo(f"    ✅ Partition table detected in converted disk")
                return True
            else:
                click.echo(f"    ⚠️  Warning: No partition table detected - attempting to fix")
                return self.attempt_boot_sector_fix(disk_path)
                
        except Exception as e:
            click.echo(f"    ⚠️  Could not verify disk structure: {e}")
            return False
    
    def attempt_boot_sector_fix(self, disk_path):
        """Attempt to fix boot sector issues in the converted disk"""
        try:
            click.echo(f"    Attempting to repair boot sector...")
            
            # Try to detect if this is a Windows disk and attempt MBR repair
            # First, check if we can detect any filesystem signatures
            result = subprocess.run([
                "file", "-s", str(disk_path)
            ], capture_output=True, text=True, check=False)
            
            if "DOS/MBR boot sector" in result.stdout or "Microsoft" in result.stdout:
                click.echo(f"    Windows/DOS boot sector detected - attempting MBR repair")
                
                # Create a backup first
                backup_path = str(disk_path) + ".backup"
                subprocess.run(["cp", str(disk_path), backup_path], check=True)
                
                # Try to use testdisk to repair the partition table
                try:
                    # Create a testdisk script to automatically repair
                    script_content = f"""select,{disk_path}
analyse
quick_search
write
quit"""
                    
                    with open("/tmp/testdisk_script.txt", "w") as f:
                        f.write(script_content)
                    
                    # Note: testdisk would need to be installed
                    # For now, we'll provide instructions to the user
                    click.echo(f"    ⚠️  Boot sector repair requires manual intervention")
                    click.echo(f"    Backup created at: {backup_path}")
                    click.echo(f"    Consider using tools like 'testdisk' or 'gparted' to repair the partition table")
                    
                except Exception as repair_error:
                    click.echo(f"    ⚠️  Automatic repair failed: {repair_error}")
                    
            else:
                click.echo(f"    ⚠️  Could not detect disk type for automatic repair")
                
            return False  # Indicate that manual intervention may be needed
            
        except Exception as e:
            click.echo(f"    ⚠️  Boot sector repair failed: {e}")
            return False
            
    def parse_vmx_config(self, vmx_file):
        """Parse VMware VMX configuration file"""
        config = {}
        try:
            # Try UTF-8 first
            with open(vmx_file, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            # Fall back to latin-1 if UTF-8 fails
            try:
                with open(vmx_file, 'r', encoding='latin-1') as f:
                    content = f.read()
            except UnicodeDecodeError:
                # Last resort: read as binary and decode with errors ignored
                with open(vmx_file, 'rb') as f:
                    content = f.read().decode('utf-8', errors='ignore')
        
        for line in content.splitlines():
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                key, value = line.split('=', 1)
                config[key.strip()] = value.strip().strip('"')
        return config
        
    def generate_libvirt_xml(self, vmx_config):
        """Generate libvirt XML configuration from VMware VMX config"""
        import uuid
        
        # Create a minimal, guaranteed-to-work libvirt XML template
        xml_template = '''<?xml version="1.0" encoding="UTF-8"?>
<domain type="kvm">
  <name>{vm_name}</name>
  <uuid>{vm_uuid}</uuid>
  <memory unit="KiB">{memory_kb}</memory>
  <currentMemory unit="KiB">{memory_kb}</currentMemory>
  <vcpu placement="static">{vcpus}</vcpu>
  <os>
    <type arch="x86_64" machine="pc-i440fx-2.9">hvm</type>
    <boot dev="hd"/>
  </os>
  <features>
    <acpi/>
    <apic/>
  </features>
  <cpu mode="host-passthrough"/>
  <clock offset="utc"/>
  <on_poweroff>destroy</on_poweroff>
  <on_reboot>restart</on_reboot>
  <on_crash>destroy</on_crash>
  <devices>
    <emulator>/usr/bin/qemu-system-x86_64</emulator>
{disk_xml}
    <interface type="network">
      <source network="default"/>
      <model type="e1000"/>
    </interface>
    <serial type="pty">
      <target port="0"/>
    </serial>
    <console type="pty">
      <target type="serial" port="0"/>
    </console>
    <input type="mouse" bus="ps2"/>
    <input type="keyboard" bus="ps2"/>
    <graphics type="vnc" port="-1" autoport="yes"/>
    <video>
      <model type="cirrus" vram="16384" heads="1" primary="yes"/>
    </video>
  </devices>
</domain>'''
        
        # Generate disk XML with absolute paths and proper escaping
        disk_xml_parts = []
        for i, disk_file in enumerate(self.disk_files):
            # Get absolute path and ensure it exists
            abs_disk_path = str(disk_file.resolve())
            if not disk_file.exists():
                raise FileNotFoundError(f"Disk file does not exist: {abs_disk_path}")
                
            # Create disk XML with IDE bus for maximum compatibility
            disk_xml = f'''    <disk type="file" device="disk">
      <driver name="qemu" type="qcow2" cache="writethrough"/>
      <source file="{abs_disk_path}"/>
      <target dev="hd{chr(97 + i)}" bus="ide"/>
    </disk>'''
            disk_xml_parts.append(disk_xml)
        
        # Get VM configuration
        memory_mb = int(vmx_config.get('memsize', '1024'))
        memory_kb = memory_mb * 1024
        vcpus = vmx_config.get('numvcpus', '1')
        vm_uuid = str(uuid.uuid4())
        
        # Format the XML template
        final_xml = xml_template.format(
            vm_name=self.vm_name,
            vm_uuid=vm_uuid,
            memory_kb=memory_kb,
            vcpus=vcpus,
            disk_xml='\n'.join(disk_xml_parts)
        )
        
        return final_xml
        
    def create_output_structure(self):
        """Create output directory structure and copy necessary files"""
        try:
            if not self.output_dir.exists():
                self.output_dir.mkdir(parents=True)
                click.echo(f"Created output directory: {self.output_dir}")
            elif self.output_dir.exists() and any(self.output_dir.iterdir()):
                if not click.confirm(f"Output directory '{self.output_dir}' is not empty. Continue?"):
                    raise click.Abort()
                    
        except PermissionError:
            raise PermissionError(f"Permission denied: Cannot create directory '{self.output_dir}'")
            
        # Copy any additional files that might be needed
        additional_files = []
        for file in self.input_dir.glob("*.*"):
            if file.suffix not in ['.vmdk', '.vmx', '.vmsd', '.log']:
                try:
                    shutil.copy2(file, self.output_dir / file.name)
                    additional_files.append(file.name)
                except Exception as e:
                    click.echo(f"Warning: Could not copy {file.name}: {e}")
                    
        if additional_files:
            click.echo(f"Copied additional files: {', '.join(additional_files)}")

@click.command()
@click.argument('input_dir', type=click.Path(exists=True, file_okay=False, dir_okay=True), 
                required=False)
@click.argument('output_dir', type=click.Path(file_okay=False, dir_okay=True), 
                required=False)
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose output')
@click.help_option('--help', '-h')
def main(input_dir, output_dir, verbose):
    """Convert VMware VM to virt-manager format
    
    INPUT_DIR: Path to directory containing VMware VM files (.vmx, .vmdk)
    OUTPUT_DIR: Path where converted virt-manager files will be created
    """
    
    # Check if arguments are provided
    if not input_dir or not output_dir:
        click.echo("Error: Both input and output directories are required.\n")
        ctx = click.get_current_context()
        click.echo(ctx.get_help())
        click.echo("\nExample usage:")
        click.echo("  python vmware_to_virt.py /path/to/vmware/vm /path/to/output")
        click.echo("  python vmware_to_virt.py ~/VMs/Windows10-VMware ~/VMs/Windows10-Libvirt")
        sys.exit(1)
        
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    converter = VMwareToVirtConverter(input_dir, output_dir)
    
    try:
        click.echo(f"Starting conversion from '{input_dir}' to '{output_dir}'")
        
        # Validate input
        converter.validate_input()
        
        # Validate VMware VM for bootability and corruption
        if not converter.validate_vmware_vm():
            click.echo("\n❌ Conversion aborted due to VM validation failure.")
            sys.exit(1)
        
        # Create output structure
        converter.create_output_structure()
        
        # Convert disk images
        converter.convert_disk_images()
        
        # Parse VMX config
        vmx_file = next(converter.input_dir.glob("*.vmx"))
        click.echo(f"Processing configuration file: {vmx_file.name}")
        vmx_config = converter.parse_vmx_config(vmx_file)
        
        # Generate libvirt XML
        xml_config = converter.generate_libvirt_xml(vmx_config)
        
        # Write XML to file
        xml_file = converter.output_dir / f"{converter.vm_name}.xml"
        with open(xml_file, 'w') as f:
            f.write(xml_config)
            
        click.echo(f"\n✅ Conversion completed successfully!")
        click.echo(f"📁 VM files converted to: {converter.output_dir}")
        click.echo(f"📄 Configuration file: {xml_file}")
        click.echo(f"\n🚀 To import and start the VM:")
        click.echo(f"   1. Define the VM: sudo virsh define {xml_file}")
        click.echo(f"   2. Start the VM: sudo virsh start {converter.vm_name}")
        click.echo(f"   3. Open virt-manager to view the VM console")
        click.echo(f"\n💡 Note: sudo is required for virsh define and start commands")
        
    except (FileNotFoundError, NotADirectoryError, PermissionError) as e:
        click.echo(f"❌ {str(e)}", err=True)
        sys.exit(1)
    except RuntimeError as e:
        click.echo(f"❌ {str(e)}", err=True)
        sys.exit(1)
    except click.Abort:
        click.echo("❌ Operation cancelled by user", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"❌ Unexpected error during conversion: {str(e)}", err=True)
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
