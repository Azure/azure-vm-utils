---
title: azure-ephemeral-disk-setup
section: 8
header: User Manual
footer: azure-ephemeral-disk-setup __VERSION__
date: __DATE__
---

# NAME

**azure-ephemeral-disk-setup** - format and mount Azure ephemeral NVMe or SCSI disks

# SYNOPSIS

**azure-ephemeral-disk-setup**

# DESCRIPTION

**azure-ephemeral-disk-setup** is a one-shot initialization service for Azure virtual machines that automatically detects, validates, formats, and mounts ephemeral local disks (NVMe or optionally SCSI). It supports multi-disk aggregation with `mdadm` and ensures safe, idempotent operation.

This intended to be configured via `/etc/azure-ephemeral-disk-setup.conf` and used early in the boot sequence (via `systemd`) to prepare local storage under a specified mount point, typically `/mnt`.

# CONFIGURATION VARIABLES

These may be set in `/etc/azure-ephemeral-disk-setup.conf` or directly exported into environment (note that any config file would override the environment):

`AZURE_EPHEMERAL_DISK_SETUP_AGGREGATION`  
: `mdadm` (default) or `none`. Defines if multiple NVMe disks are aggregated into RAID-0.

`AZURE_EPHEMERAL_DISK_SETUP_FS_TYPE`  
: Filesystem to use: `ext4` (default) or `xfs`.

`AZURE_EPHEMERAL_DISK_SETUP_MDADM_CHUNK`  
: RAID chunk size, e.g., `512K`, `1M`. Default is `512K`.

`AZURE_EPHEMERAL_DISK_SETUP_MDADM_NAME`  
: RAID name, default: `azure-ephemeral-md`.

`AZURE_EPHEMERAL_DISK_SETUP_MOUNT_POINT`  
: Mount path, default: `/mnt`.

`AZURE_EPHEMERAL_DISK_SETUP_NVME_MODEL_DETECTION`  
: If `true`, uses NVMe model detection if symlinks are missing.

`AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE`  
: If `true`, will fall back to SCSI resource disk if no NVMe disks are available.

# DETAILS

The service performs the following steps in order:

1. **Load Configuration**:
   - From `/etc/azure-ephemeral-disk-setup.conf` if it exists.
   - There is restrictive filtering to minimize risk of bad configuration: `source <(grep -E '^AZURE_EPHEMERAL_DISK_SETUP_[A-Z_]+=["'"'"'A-Za-z0-9_./:-\ ]+$' "${CONFIGURATION_FILE}")`

2. **Validate configuration**:
   - Ensure configuration appears to be valid.

3. **Check Existing Mounts**:
   - If the mount point is already mounted **and** the corresponding `/etc/fstab` entry includes the comment `comment=azure-ephemeral-disk-setup`, it exits with success.
   - If mounted or defined by another service, it exits with an error.

4. **Disk Detection**:
   - NVMe disks are discovered via `/dev/disk/azure/local/by-serial/*`.
     - If `AZURE_EPHEMERAL_DISK_SETUP_NVME_MODEL_DETECTION=true`: NVMe model strings are used to detect disks (to support cases where azure-vm-utils is not installed).
   - If no NVMe and `AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true`, SCSI resource disk is discovered via `/dev/disk/azure/resource`.

5. **Disk Validation**:
   - NVMe local disks must be:
     - block devices
     - not mounted
     - not partitioned
     - not already formatted
   - SCSI resource disk has an exception for pre-formatted NTFS disks and must be:
     - empty other than `dataloss_warning_readme.txt` and `System Volume Information`
     - not mounted
     - single partition

6. **Aggregation (if configured)**:
   - If more than one NVMe local disk is found and `AZURE_EPHEMERAL_DISK_SETUP_AGGREGATION=mdadm`, creates a RAID-0 array with:
     - Metadata version 1.2
     - Chunk size per configuration
     - Name per configuration
     - Exported as `/dev/md/<name>_0`

7. **Filesystem Formatting**:
   - Formats the target device with the configured filesystem.
   - Forced formatting is only allowed for SCSI disks with verified NTFS contents.

8. **Mounting and fstab Update**:
   - Creates the mount point directory.
   - Old entries with `comment=azure-ephemeral-disk-setup` are removed.
   - Adds a line to `/etc/fstab` using:
     ```
     <device> <mount_point> <fs_type> defaults,nofail,comment=azure-ephemeral-disk-setup 0 2
     ```
   - Mounted directly to mount point to support images with read-only fstab.

# EXIT STATUS

**0** – Success  
**1** – Configuration or device validation error  

# EXAMPLES

Detect and format ephemeral disks using default settings:

```bash
$ sudo azure-ephemeral-disk-setup
````

Configure SCSI resource disk fallback:

```conf
# /etc/azure-ephemeral-disk-setup.conf
AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true
AZURE_EPHEMERAL_DISK_SETUP_FS_TYPE=ext4
AZURE_EPHEMERAL_DISK_SETUP_MOUNT_POINT=/mnt
```

Example fstab entry after setup of SCSI resource disk:

```fstab
/dev/disk/azure/resource /mnt xfs defaults,nofail,comment=azure-ephemeral-disk-setup 0 2
```

Example fstab entry after setup of multiple local NVMe disks:

```fstab
/dev/md/azure-ephemeral-md_0 /mnt xfs defaults,nofail,comment=azure-ephemeral-disk-setup 0 2
```

# FILES

`/etc/azure-ephemeral-disk-setup.conf`
: Optional user configuration file.

`/etc/fstab`
: Mount persistence configuration.

# DEBUGGING

The service may be debugged using `bash -x`:

```bash
$ sudo bash -x azure-ephemeral-disk-setup
````

# SEE ALSO

**mdadm(8)**, **mount(8)**, **cloud-init(8)**, **waagent(8)**

Project home: [https://github.com/Azure/azure-vm-utils](https://github.com/Azure/azure-vm-utils)