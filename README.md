# VMware to Virt-Manager VM Converter

A Python tool to convert VMware virtual machines to virt-manager (libvirt) compatible format with comprehensive validation and error handling.

## Features

- **Pre-conversion validation**: Detects corrupted or non-bootable VMware VMs before conversion
- Converts VMware .vmdk disk images to .qcow2 format
- Generates libvirt XML domain configuration from VMware .vmx files
- Handles both split disk and single disk VMDK formats
- Automatic disk format detection and conversion
- Boot sector preservation for bootable VMs
- Comprehensive error handling and progress reporting

## Requirements

### System Dependencies
- `qemu-img` (part of QEMU utilities)
- Python 3.6 or higher
- `libvirt` and `virt-manager` (for running converted VMs)

### Python Dependencies
- `click`
- `defusedxml`

## Installation

### Linux

1. Install system dependencies:
   ```bash
   # Ubuntu/Debian
   sudo apt-get install qemu-utils python3-pip libvirt-daemon-system virt-manager
   
   # CentOS/RHEL
   sudo yum install qemu-img python3-pip libvirt virt-manager
   
   # Fedora
   sudo dnf install qemu-img python3-pip libvirt virt-manager
   
   # Arch Linux
   sudo pacman -S qemu-img python-pip libvirt virt-manager
   ```

2. Install Python dependencies:
   ```bash
   pip3 install -r requirements.txt
   ```

3. Enable and start libvirt service:
   ```bash
   sudo systemctl enable libvirtd
   sudo systemctl start libvirtd
   ```

### Windows

**Note**: This tool is primarily designed for Linux. For Windows users:

1. **Option 1 - WSL2 (Recommended)**:
   - Install WSL2 with Ubuntu
   - Follow Linux installation steps within WSL2
   - Access Windows VMware VMs via `/mnt/c/path/to/vms`

2. **Option 2 - Native Windows**:
   - Install QEMU for Windows: https://qemu.weilnetz.de/w64/
   - Add QEMU to PATH
   - Install Python 3.x from python.org
   - Run: `pip install -r requirements.txt`
   - **Note**: You'll still need a Linux system to run the converted VMs with libvirt

### macOS

```bash
# Install via Homebrew
brew install qemu python3
pip3 install -r requirements.txt
```

**Note**: libvirt/virt-manager support on macOS is limited. Consider using Linux VM or Docker.

## Usage

```bash
python3 vmware_to_virt.py <input_vmware_dir> <output_dir>
```

### Example
```bash
python3 vmware_to_virt.py ~/VMs/Windows10-VMware ~/VMs/Windows10-Libvirt
```

### Options
- `--verbose, -v`: Enable verbose output for debugging
- `--help, -h`: Show help message

## VM Management with libvirt

### Import and Start VM

After conversion, manage the VM using `virsh` commands (**requires sudo**):

```bash
# Define the VM in libvirt
sudo virsh define /path/to/output/vm.xml

# List all VMs
sudo virsh list --all

# Start the VM
sudo virsh start VM_NAME

# Open virt-manager GUI
virt-manager
```

### VM Management Commands

```bash
<<<<<<< HEAD
# Start VM
sudo virsh start VM_NAME

# Shutdown VM (graceful)
sudo virsh shutdown VM_NAME

# Force stop VM
sudo virsh destroy VM_NAME

# Pause/suspend VM
sudo virsh suspend VM_NAME

# Resume VM
sudo virsh resume VM_NAME

# Get VM info
sudo virsh dominfo VM_NAME

# Edit VM configuration
sudo virsh edit VM_NAME
=======
sudo virsh define /path/to/output/vm_name.xml
>>>>>>> 5ebeb1f6f0c28d4632ed44ffe2899d21d50187b8
```

### Remove VM Completely

```bash
# Stop the VM if running
sudo virsh destroy VM_NAME

# Undefine (remove) the VM from libvirt
sudo virsh undefine VM_NAME

# Optionally remove disk files
rm /path/to/vm/disk.qcow2
```

### Network Management

```bash
# Start default network
sudo virsh net-start default

# Set default network to autostart
sudo virsh net-autostart default

# List networks
sudo virsh net-list --all
```

## Pre-Conversion Validation

The converter now includes comprehensive validation that checks:

- ✅ **Partition table presence**: Ensures VMDK has valid partition structure
- ✅ **Boot sector integrity**: Verifies bootable disk signatures
- ⚠️ **VM state warnings**: Detects suspended/crashed VM states
- ⚠️ **Memory dump detection**: Identifies VMs that weren't properly shut down
- ❌ **Corruption detection**: Stops conversion of corrupted/non-bootable VMs
- 🔒 **Encryption detection**: Identifies encrypted VMs that cannot be converted

### Validation Failure Resolution

If validation fails:

1. **Boot the VM in VMware first** to verify it works
2. **Properly shut down the VM** (don't suspend or force-close)
3. **Delete snapshots** and memory files (.vmem, .vmss)
4. **Use VMware's disk repair tools** if corruption is detected
5. **Consolidate snapshots** in VMware before conversion

## Troubleshooting

### Common Issues

1. **"qemu-img not found"**
   - Install qemu-utils package as shown in installation section

2. **"Permission denied" when using virsh**
   - All `virsh` commands require `sudo` privileges
   - Ensure you're in the `libvirt` group: `sudo usermod -a -G libvirt $USER`

3. **"Network 'default' not found"**
   - Start the default network: `sudo virsh net-start default`
   - Set it to autostart: `sudo virsh net-autostart default`

4. **"VM validation failed"**
   - The source VMware VM is corrupted or non-bootable
   - Follow validation failure resolution steps above

5. **"No bootable device" after conversion**
   - Original VMware VM lacks proper boot sector/partition table
   - Verify VM boots in VMware before conversion

6. **"VM appears to be encrypted" validation error**
   - VMware VM is encrypted and cannot be converted directly
   - **Solution**: Decrypt the VM in VMware first:
     - **VMware Workstation**: VM > Settings > Options > Encryption > Decrypt
     - **VMware ESXi**: Use vSphere Client to remove encryption
     - **VMware Fusion**: VM > Settings > Encryption > Decrypt
   - Re-run conversion after decryption

7. **Conversion hangs or is very slow**
   - Large disk files (>50GB) can take 10-30 minutes
   - Ensure sufficient disk space (2x source disk size)
   - Check system resources (CPU/RAM/disk I/O)

### File Structure

**Input (VMware VM directory)**:
- `*.vmx` - VMware configuration file (required)
- `*.vmdk` - VMware disk image(s) (required)
- `*.vmsd` - VMware snapshot metadata (optional)
- `*.vmem` - Memory dumps (indicates suspended VM - warning)
- `*.vmss` - Snapshot state (indicates suspended VM - warning)

**Output (Converted VM directory)**:
- `*.qcow2` - Converted disk image(s)
- `*.xml` - Libvirt domain configuration

## Supported VMware Formats

- ✅ Single monolithic VMDK files
- ✅ Split VMDK files (descriptor + data files)
- ✅ VMware Workstation/Player VMs
- ✅ VMware ESXi exported VMs
- ✅ VMware Fusion VMs (macOS)

## Limitations

- **Encrypted VMs are not supported** (must be decrypted in VMware first)
- Snapshots are not converted (consolidate in VMware first)
- USB device mappings are not preserved
- VMware Tools integration is lost (install virtio drivers instead)
- Some advanced VMware features may not have libvirt equivalents
- Requires properly shut down, bootable source VMs
- Windows-specific: Requires Linux system for running converted VMs

## Security Notes

- `sudo` is required for `virsh` commands due to libvirt security model
- Converted VMs run with KVM hypervisor privileges
- Disk files should be stored in libvirt's managed directories
- Consider SELinux/AppArmor policies for additional security

## Performance Tips

- Use SSD storage for faster conversion
- Ensure adequate RAM (4GB+ recommended)
- Close unnecessary applications during conversion
- Use `--verbose` flag to monitor progress
- Convert VMs during low system usage periods

## License

MIT License - see LICENSE file for details.
