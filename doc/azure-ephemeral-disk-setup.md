---
title: azure-ephemeral-disk-setup
section: 8
header: User Manual
footer: azure-ephemeral-disk-setup __VERSION__
date: __DATE__
---

# NAME

**azure-ephemeral-disk-setup** — detect, validate, format, and mount Azure ephemeral local disks (NVMe or SCSI) with optional RAID aggregation

# SYNOPSIS

```bash
azure-ephemeral-disk-setup
````

# DESCRIPTION

**azure-ephemeral-disk-setup** is a systemd-managed one-shot initialization service for Microsoft Azure virtual machines that prepares ephemeral (temporary) disks for use. It supports both NVMe and SCSI ephemeral disks and is capable of aggregating multiple NVMe devices into a RAID-0 array using `mdadm`.

The service is opt-in and should be configured through `/etc/azure-ephemeral-disk-setup.conf`. It runs early in the boot process and aims to be idempotent, safe, and compatible with existing tools such as `cloud-init` and `WALinuxAgent`.

Logs are printed to stderr and are accessible via journalctl if using the systemd service:

```bash
journalctl -u azure-ephemeral-disk-setup.service
```

# CONFIGURATION

Configuration is loaded from:

* `/etc/azure-ephemeral-disk-setup.conf` (preferred)
* Environment variables (fallback)

The following environment variables are supported:

* **AZURE\_EPHEMERAL\_DISK\_SETUP\_AGGREGATION**
  Supported values: `mdadm`
  Default: `mdadm` (only supported value; enables aggregation of local NVMe disks when multiple are found)

* **AZURE\_EPHEMERAL\_DISK\_SETUP\_FS\_TYPE**
  Supported values: `ext4`, `xfs`
  Default: `ext4` (universally available; `xfs` requires `xfsprogs`)

* **AZURE\_EPHEMERAL\_DISK\_SETUP\_MDADM\_CHUNK**
  Supported values: Any valid mdadm chunk size
  Default: `512K` (mdadm default)

* **AZURE\_EPHEMERAL\_DISK\_SETUP\_MDADM\_NAME**
  Supported values: Any valid mdadm name
  Default: `azure-ephemeral-md`

* **AZURE\_EPHEMERAL\_DISK\_SETUP\_MOUNT\_POINT**
  Supported values: Any valid mount point path
  Default: `/mnt` (matches cloud-init default mount point)

* **AZURE\_EPHEMERAL\_DISK\_SETUP\_SCSI\_RESOURCE**
  Supported values: `true`, `false`
  Default: `false` (minimizes risk of conflict with cloud-init and WALinuxAgent)

# OPERATION

The service performs the following steps:

### 1. Load and Validate Configuration

* Configuration is read via filtered `source /etc/azure-ephemeral-disk-setup.conf`, allowing only safe environment-style assignments.
* If invalid values are detected, the service exits with error.
* Required tools (`mkfs.${AZURE_EPHEMERAL_DISK_SETUP_FS_TYPE}`, `mdadm`) must be available.

### 2. Check for Existing Mounts

If the mount point is already configured:

* with a matching `/etc/fstab` line containing the comment `comment=azure-ephemeral-disk-setup`, the service exits with success after waiting for mount to complete.
* by cloud-init and source is `/dev/disk/cloud/azure_resource-part1`:

  * if `AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=false`, the service exits with success allowing cloud-init to manage the disk.
  * if `AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true`, the service exits with error as the entry is either stale or conflicting

* by other tools/services/configuration, the service exits with error.

### 3. Detect and Validate Disks

**NVMe** disks are detected via:

* Model names:

   * Microsoft NVMe Direct Disk
   * Microsoft NVMe Direct Disk v2

**SCSI resource disk** is detected and validated if `AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true` and no ephemeral NVMe disks are detected.

See **SAFETY AND VALIDATION** section for more details on how disks are validated to ensure no data is lost.

### 4. Disk Setup

Each candidate disk is checked to ensure:

* It is a block device
* It is not mounted
* It is not partitioned (unless NTFS resource disk)
* It has no existing filesystem (unless NTFS resource disk)

If any disk fails these checks, the service aborts with a detailed error.

### 5. Aggregation with RAID-0 For VMs with Multiple local NVMe Disks

If more than one NVMe disk is found and aggregation is enabled with mdadm:

```bash
mdadm --create "/dev/md/${AZURE_EPHEMERAL_DISK_SETUP_MDADM_NAME}_0" \
  --level=0 \
  --raid-devices=N \
  --metadata=1.2 \
  --chunk="$AZURE_EPHEMERAL_DISK_SETUP_MDADM_CHUNK" \
  --name="$AZURE_EPHEMERAL_DISK_SETUP_MDADM_NAME" \
  ${DISKS[@]}
```

Configuration is **not** written to `/etc/mdadm/mdadm.conf` in favor of kernel auto-detection.

### 6. Format Filesystem

* Formats target device (either RAID device or single disk) directly **without partitioning**
* Uses `mkfs.ext4 [-F] -L AzureEphmDsk ...` or `mkfs.xfs [-f] -L AzureEphmDsk ...` with the force flag only if it is reformatting the SCSI resource disk

### 7. Persistenting Mount

If `/etc/fstab` is writable:

* Previous entries with `comment=azure-ephemeral-disk-setup` are removed
* New entry added:

   ```fstab
   LABEL=AzureEphmDsk <mount_point> <fs_type> defaults,nofail,comment=azure-ephemeral-disk-setup 0 2
   ```

If `/etc/fstab` is read-only or does not exist, it will not be updated.  It will be mounted by this service on every boot.

### 8. Mounting

For persistent mounts:

* Tries to mount using systemd (`systemctl start <mount.unit>`)
* Falls back to direct `mount` call if mount unit fails to start

For non-persitent mounts, a `mount` call is used.

# SAFETY AND VALIDATION

This service only formats NVMe disks that are:

* Not mounted
* Unpartitioned
* Unformatted

SCSI resource disks are only reformatted if it:

* Has a single NTFS partition labeled `Temporary Storage`
* Is empty except for `dataloss_warning_readme.txt` and `System Volume Information`

   * To check if disk is empty, this service will attempt to mount the resource disk partition read-only via `ntfs3`, with fallback to `ntfs`. If both fail due to lack of driver, it is assumed safe to reformat.

Calls to mkfs and mdadm do not use `--force` for formatting or mdadm array creation unless reformatting validated NTFS SCSI disk.

# EXIT STATUS

* `0` — Success
* `1` — Any error (invalid config, conflicting mount, unsafe disk, etc.)

# FSTAB STRATEGY

The following values are used when generating an `/etc/fstab` entry for the ephemeral disk:

* **fs\_spec**: `LABEL=AzureEphmDsk`
  Refers to the disk label. This assumes the script has ownership of the `AzureEphmDsk` label.

* **fs\_vfstype**: `$AZURE_EPHEMERAL_DISK_SETUP_FS_TYPE`
  The filesystem type, determined by configuration (e.g., `ext4` or `xfs`).

* **fs\_mntops**: `defaults,nofail,comment=azure-ephemeral-disk-setup`

  * `defaults`: standard mount options
  * `nofail`: ensures the VM boots even if the ephemeral disk is missing or has been re-allocated
  * `comment=azure-ephemeral-disk-setup`: tags the entry to show it's managed by this setup

* **fs\_freq**: `0`
  Disables `dump` backups for the filesystem.

* **fs\_passno**: `2`
  Sets the order for `fsck` during boot. Non-root filesystems typically use `2`.

# AVOIDING CONFLICTS WITH CLOUD-INIT

If `AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=false`, this service will exit with success if cloud-init is managing the SCSI resource disk at the same mount point. Given the widespread usage of cloud-init for managing the SCSI resource disk, this is the default case.

If `AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true`, cloud-init management of the resource disk must be disabled. There are two options for disabling cloud-init's management of SCSI resource disk:

## Disabling cloud-init management of SCSI resource disk via udev rules

Disable udev rules responsible for creating the /dev/disk/cloud symlinks:

```bash
ln -sf /dev/null /etc/udev/rules.d/66-azure-ephemeral.rules
```

If cloud-init doesn't detect the device, it will not attempt to format/mount it.

## Disabling cloud-init management of SCSI resource disk via cloud-init configuration (cloud-init >= 25.3)

Work is ongoing to introduce a flag to the Azure datasource to control behavior. See [pull request](https://github.com/canonical/cloud-init/pull/6323).

This is expected to be available in cloud-init 25.3.

# AVOIDING CONFLICTS WITH WALINUXAGENT

WALinuxAgent must be configured with `ResourceDisk.Format=n`.

If `AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true`, this service will exit with error if `/etc/waagent.conf` sets `ResourceDisk.Format=y`.

# EXAMPLES

Basic usage:

```bash
sudo azure-ephemeral-disk-setup
```

Enable management of SCSI resource disk:

```conf
# /etc/azure-ephemeral-disk-setup.conf
AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true
```

# FILES

* `/etc/azure-ephemeral-disk-setup.conf` — user configuration
* `/etc/fstab` — mount persistence

# SERVICE ORDERING

`DefaultDependencies=no` to avoid typical service dependencies as we want to start early.

After:

- `cloud-init.service` (a.k.a. `cloud-init-network.service`) allows users to customize service configuration using cloud-config
- `local-fs.target` ensures local filesystems are mounted (necessary if no cloud-init)

Before:

- `cloud-init.target` ensures we start before cloud-init completes which services may use to determine if system is fully configured
- `walinuxagent.service waagent.service` ensures we start prior to walinuxagent and avoid conflicts
- `network-online.target` to ensure we start before networking is considered online
- `sshd.service` to ensure we start before sshd starts accepting connections
- `systemd-user-sessions.service` to ensure we start before user sessions are enabled
- `sysinit.target` to ensure we run before most services requiring mounts (Debian/Ubuntu only)

# DEBUGGING

All logs are written to stderr and accessible with:

```bash
journalctl -u azure-ephemeral-disk-setup.service
```

# SEE ALSO

**mdadm(8)**, **mount(8)**, **cloud-init(8)**, **waagent(8)**

Project Home: [https://github.com/Azure/azure-vm-utils](https://github.com/Azure/azure-vm-utils)
