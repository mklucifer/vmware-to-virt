# VMware to Virt-Manager Converter

A Python utility to convert VMware virtual machines to virt-manager (libvirt) compatible format.

## What it does

This program converts VMware VM files to work with virt-manager/libvirt by:

1. **Converting disk images**: Transforms `.vmdk` files to `.qcow2` format using `qemu-img`
2. **Translating configuration**: Converts VMware `.vmx` configuration files to libvirt XML format
3. **Preserving VM settings**: Maintains memory, CPU, and other VM configuration settings
4. **Creating importable structure**: Generates a complete VM directory ready for virt-manager import

## Requirements

- Python 3.6+
- `qemu-img` utility (part of QEMU package)
- Required Python packages (see requirements.txt)

### Installing Dependencies

#### System Dependencies
```bash
# Ubuntu/Debian
sudo apt-get install qemu-utils

# CentOS/RHEL/Fedora
sudo yum install qemu-img
# or
sudo dnf install qemu-img

# Arch Linux
sudo pacman -S qemu
```

#### Python Dependencies
```bash
pip install -r requirements.txt
```

## Usage

### Basic Usage
```bash
python vmware_to_virt.py <input_directory> <output_directory>
```

### Examples
```bash
# Convert a VMware VM to virt-manager format
python vmware_to_virt.py /path/to/vmware/vm /path/to/converted/vm

# Example with actual paths
python vmware_to_virt.py ~/VMs/Windows10-VMware ~/VMs/Windows10-Libvirt
```

### Command Line Help
```bash
python vmware_to_virt.py --help
```

## Input Requirements

The input directory must contain:
- At least one `.vmx` file (VMware configuration)
- At least one `.vmdk` file (VMware disk image)

Optional files that will be preserved:
- `.nvram` files (BIOS/UEFI settings)
- `.vmsd` files (snapshot metadata)
- Other auxiliary files

## Output Structure

The output directory will contain:
- `.qcow2` files (converted disk images)
- `.xml` file (libvirt domain configuration)
- Any additional files from the original VM

## Importing to Virt-Manager

After conversion:

1. Open virt-manager
2. Go to **File** → **Open** or **Import Existing Virtual Machine**
3. Select the generated `.xml` file from the output directory
4. Follow the import wizard to complete the process

Alternatively, use virsh command line:
```bash
virsh define /path/to/output/vm_name.xml
```

## Supported VMware Formats

- VMware Workstation VMs
- VMware Player VMs
- VMware Fusion VMs (basic support)

## Limitations

- Snapshots are not converted (only base disk images)
- Some advanced VMware features may not have libvirt equivalents
- Network configuration may need manual adjustment
- USB device mappings are not preserved

## Troubleshooting

### Common Issues

**Error: "qemu-img: command not found"**
- Install qemu-utils package (see Requirements section)

**Error: "No .vmx file found"**
- Ensure the input directory contains VMware VM files
- Check that you're pointing to the VM directory, not individual files

**Error: "Permission denied"**
- Ensure you have read access to input directory
- Ensure you have write access to output directory

**Conversion fails with disk errors**
- Check that .vmdk files are not corrupted
- Ensure sufficient disk space for conversion

### Getting Help

For issues or questions:
1. Check that all requirements are installed
2. Verify input directory structure
3. Run with `--help` for usage information
4. Check system logs for detailed error messages

## License

This project is open source. Feel free to modify and distribute according to your needs.
