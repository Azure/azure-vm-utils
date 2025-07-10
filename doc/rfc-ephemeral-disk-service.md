# Azure Local Disk Formatting Service

## Overview

This proposed service formats and mounts local ephemeral NVMe disks on Azure VMs.

For safety, this service will be opt-in (disabled by default) and instructions will be made available on how to enable it.

## Background

The primary ways to configure local/resource disks on Linux include:

* `cloud-init`, most commonly used for managing SCSI resource disk
* `WALinuxAgent`, uncommonly used for managing SCSI resource disk
* custom services/scripts like those done by HPC

### Azure Disk Types

There are few classes of disks that Azure supports:

| Disk Type                                | SCSI | NVMe | Description                                             |
|------------------------------------------|:----:|:----:|---------------------------------------------------------|
| OS disk                                  |  X   |  X   | Usually remote, but may be ephemeral local              |
| Data disk(s)                             |  X   |  X   | Customer-configured disk(s) assigned a LUN and name     |
| Resource disk                            |  X   |  -   | Ephemeral SCSI disk                                     |
| Temp (a.k.a. local, ephemeral) disks(s)  |  X   |  X   | Ephemeral NVMe disk(s)                                  |


### Ephemeral Disk Scenarios

The scenarios to consider based on existing VM sizes:

| Scenario                                  | Example VM Size     |
| ----------------------------------------- | ------------------- |
| (a) No SCSI or NVMe resource disk         | Standard\_D2s\_v4   |
| (b) SCSI resource disk                    | Standard\_D2ds\_v4  |
| (c) SCSI + NVMe local disk                | Standard\_L8s\_v3   |
| (d) SCSI + multiple NVMe local disks      | Standard\_L80s\_v3  |
| (e) No SCSI or NVMe resource disk (newer) | Standard\_D2s\_v6   |
| (f) Single NVMe local disk                | Standard\_D2ds\_v6  |
| (g) Multiple NVMe local disks             | Standard\_D48ds\_v6 |

### SCSI Resource Disk Handling: cloud-init

Cloud-init detects the SCSI resource disk, partitions it, formats it ext4, and mounts it to /mnt.  Some images have been known to reconfigure this default mount point to /mnt/resource.

The Azure datasource configures the following as a default:

```json
  "disk_aliases": {"ephemeral0": "/dev/disk/cloud/azure_resource"},
```

The Azure data source does this by dynamically including the following configuration if `/dev/disk/cloud/azure_resource` is detected:

```json
  "disk_setup": {
    "ephemeral0": {
      "table_type": "gpt",
      "layout": [100],
      "overwrite": True,
    },
  },
  "fs_setup": [{"filesystem": "ext4", "device": "ephemeral0.1"}],
```

The resulting fstab entry looks like:

```fstab
/dev/disk/cloud/azure_resource-part1    /mnt    auto    defaults,nofail,x-systemd.requires=cloud-init.service,_netdev,comment=cloudconfig   0       2
```

If no resource disk is present, no disk is formatted or added to `/etc/fstab`.

NVMe devices can be configured by cloud-config, but would not be re-initialized if VM is re-allocated.

### SCSI Resource Disk Handling: WALinuxAgent

WALinuxAgent supports automatic configuration of SCSI resource disk with the following parameters:

```ini
# Format if unformatted. If 'n', resource disk will not be mounted.
ResourceDisk.Format=y

# File system on the resource disk
# Typically ext3 or ext4. FreeBSD images should use 'ufs2' here.
ResourceDisk.Filesystem=ext4

# Mount point for the resource disk
ResourceDisk.MountPoint=/mnt/resource

# Create and use swapfile on resource disk.
ResourceDisk.EnableSwap=n

# Size of the swapfile.
ResourceDisk.SwapSizeMB=0

# Comma-seperated list of mount options. See mount(8) for valid options.
ResourceDisk.MountOptions=None
```

Note that this does allow for configuration of swap space on resource disk, a feature cloud-init does not directly support.

Additional notes:

- WALinuxAgent does not write to `/etc/fstab`.

- WALinuxAgent does not write to unpartitioned disks.

- WALinuxAgent does not write to disk if already mounted.

### NVMe Disk Handling

Neither cloud-init or WALinuxAgent directly manage NVMe disks.  Custom cloud-config can be used to configure NVMe disks, for example:

```yaml
#cloud-config
fs_setup:
  - label: local1
    filesystem: ext4
    device: /dev/disk/azure/local/by-index/1

mounts:
  - [ "/dev/disk/azure/local/by-index/1", "/mnt", "ext4", "defaults,nofail,x-systemd.makefs", "0", "2" ]
```

In this example, `x-systemd.makefs` is used to ensure systemd formats the disk if VM is reallocated.

# Design

## Goals

The goals for the design are as follows:

* Automatic detection, formatting and mounting of ephemeral disks.
* Aggregate multiple local NVMe disks with mdadm using RAID-0.
* Support configurable filesystem types and mount points.
* Configurable knobs to gracefully handle potential conflicts with `cloud-init` and `WALinuxAgent`.
* Minimize boot performance impact.
* Reliable booting and graceful handling of stale or incorrect configurations.

## Systemd Service

Unit: `azure-ephemeral-disk-setup.service`

```ini
[Unit]
Description=Format and mount local ephemeral NVMe disks
After=cloud-init.service cloud-init-network.service local-fs.target
Before=walinuxagent.service waagent.service sysinit.target
DefaultDependencies=no

[Service]
Type=oneshot
ExecStart=/usr/sbin/azure-ephemeral-disk-setup
RemainAfterExit=yes
StandardOutput=journal+console
StandardError=journal

[Install]
WantedBy=sysinit.target
```

### Service Ordering

After:

- `cloud-init.service` (aka `cloud-init-network.service`) allows users to customize service configuration using cloud-config.
- `local-fs.target` ensures local filesystems are mounted (necessary if no cloud-init).

Before:

- `walinuxagent.service waagent.service` ensures we start prior to walinuxagent and avoid conflicts.
- `sysinit.target` to ensure we run before most services requiring mounts.

## Service Configuration

To allow for some flexibility for customers, we initially intend to support a number of environment variables to control behaviors:

| Variable Name                                   | Supported Values           | Default Value      | Description                                                                                             |
|-------------------------------------------------|----------------------------|--------------------|---------------------------------------------------------------------------------------------------------|
| AZURE_EPHEMERAL_DISK_SETUP_AGGREGATION          | mdadm                      | mdadm              | Aggregation mode for local NVMe disks if multiple are found                                                    |
| AZURE_EPHEMERAL_DISK_SETUP_FS_TYPE              | ext4, xfs                  | ext4               | Filesystem to format the volume                                                                         |
| AZURE_EPHEMERAL_DISK_SETUP_MDADM_CHUNK          | Any valid mdadm chunk size | 512K               | mdadm --chunk <chunk size>                                                                          |
| AZURE_EPHEMERAL_DISK_SETUP_MDADM_NAME           | Any valid mdadm name       | azure-ephemeral-md | mdadm --name <name>                                                                         |
| AZURE_EPHEMERAL_DISK_SETUP_MOUNT_POINT          | Any valid mount point path | /mnt               | Where to mount the final volume                                                                         |
| AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE        | true, false                | false              | If true, manage SCSI resource disk.                                                                          |

### Service Configuration Path

Option A: `/etc/default/azure-ephemeral-disk-setup`

Option B: `/etc/azure-ephemeral-disk-setup.service`

- A bit more intuitive to find than `/etc/default`?

Option C: `/etc/azure/ephemeral-disk-setup.service`

- Longer term organization of azure-* configs?

## Disk Aggregation

To support a simplfiied user experience when using a VM size with multiple NVMe disks, disk aggregation will be used.

RAID-0, or striping, will be used to take advantage of available disk space and maximize performance for most scenarios.

The two most common tools to enable disk aggregation are `mdadm` and `LVM`.

### mdadm

Pros:

* Software RAID support
* Excellent performance
* Simple and robust for RAID-only tasks

Cons:

* No volume resizing or snapshotting
* Lacks advanced volume management features

### LVM (Logical Volume Manager)

Pros:

* Flexible volume resizing and snapshots
* Easy to manage logical volumes
* Can work over RAID (including mdadm arrays)

Cons:

* Slightly more complex setup
* Performance overhead compared to raw devices or mdadm in some cases

### Verdict: mdadm

Generally speaking, `mdadm` provides slightly better performance while `LVM` provides more flexibility.

Most of the additional functionality that `LVM` provides isn't relevant to ephemeral disk aggregation, so we will initially only support `mdadm`.

To create mdadm array, the following command will be used:

```bash
mdadm --create /dev/md0 \
  --level=0 \
  --raid-devices=<disks> \
  --metadata=1.2 \
  --chunk=$AZURE_EPHEMERAL_DISK_SETUP_MDADM_CHUNK \
  --name=$AZURE_EPHEMERAL_DISK_SETUP_MDADM_NAME
```

Earlier metadata versions allow for some bootable cases which are not relevant.  Use the latest version (1.2). If a new version comes along in the future, we can expose this too.

We will make use of mdadm automatic detection and _not_ write array configuration to `/etc/mdadm/mdadm.conf`.  This removes a touch point for reallocations, image creation, etc.

## Disk Partitioning

Disks will not be partitioned.  The block device will be formatted directly to avoid partitioning complexity.

## Disk Detection Logic

There are two potential methods to detect NVMe local disks via:

* by-serial symlink
* device models

### Option A: By-Serial

Disks are filtered via by-serial labels:

* `/dev/disk/azure/local/by-serial/*`

This will require udevadm settle to ensure links are available, depending on ordering.

Command:

```bash
lsblk -d -o NAME,MODEL | grep -E 'Microsoft NVMe Direct Disk( v2)?'
```

Note that we are using `by-serial` rather than `by-index` or `by-name` because these are not available on Direct Disk v1.

The advantage of this is that making use of symlinks removes a touch point for future models of direct disks.

### Option B: By-Model

Disks are filtered by model string:

* Microsoft NVMe Direct Disk
* Microsoft NVMe Direct Disk v2

The advantage of this is that the service will function without azure-vm-utils' udev rules.

## Conflict Detection Handling if SCSI Resource Disk Detected

### Conflict A: WALinuxAgent Configured to Format the Resource Disk (NVMe or No NVMe)

WALinuxAgent will check if the resource disk is mounted already and skip setup. However, if the NVMe disks are formatted and mounted, this will not prevent WALinuxAgent from mounting over our mount point.

Mitigation: check if `/etc/waagent.conf`contains `ResourceDisk.Format=y` with [allowed syntax](https://github.com/Azure/WALinuxAgent/blob/2aa5926cbf7cc6452ac2c8cf0cd81a63bfec7146/azurelinuxagent/common/conf.py#L44).

```bash
grep -q '^[[:space:]]*ResourceDisk\.Format[[:space:]]*=[[:space:]]*y[[:space:]]*\(#.*\)\?$' /etc/waagent.conf
```

The WALinuxAgent service will be assumed to be enabled because (nearly) every image uses it and some images may start the service independent of systemd configuration (Flatcar).

If WALinuxAgent *already* formatted the resource disk, a VM re-allocation will be necessary to shift ownership to `azure-ephemeral-disk-setup.service`.

### Conflict B: Cloud-Init Formats Resource Disk (first), AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true, No NVMe, Matching Mount Point

Mitigation: the mount source will be checked to match $(readlink -f /dev/disk/azure/resource).

If matching, exit with success, else exit with failure.

```bash
resource_disk="$(readlink -f /dev/disk/azure/resource)"
mount_source="$(findmnt $AZURE_EPHEMERAL_DISK_SETUP_MOUNTPOINT -o SOURCE --noheadings)"

if [[ $resource_disk != $mount_source ]]; then
  exit_failure
fi
```

### Conflict C: Cloud-Init Formats Resource Disk (first), AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true, No NVMe, Mismatched Mount Point

If cloud-init formatted the resource disk with a different mount point, the disk will be in use and will fail to format resulting in service error.

Mitigation: None - exit with failure when format fails.

### Conflict D: Cloud-Init Formats Resource Disk (first), With NVMe, Matching Mount Point

Cloud-init formatted the resource disk with matching mount point.

Mitigation: If target mount point is already mounted, check source device and exit with error if unexpected device.

### Conflict E: Cloud-Init Formats Resource Disk (first), With NVMe, Mismatched Mount Point

Cloud-init formatted the resource disk with different mount point.

This results in an uneccessary mount, and conflict only arises if mounts are dependent and ordered wrong (e.g. /mnt/resource under /mnt).

Mitigation: This falls into the realm of user responsibility, no checks will be performed. Document.

## Cloud-init Workarounds to Proactively Avoid Conflicts

To avoid conflicts with the SCSI resource disk, it would be best to disable cloud-init's configuration of SCSI resource disk.  There is no great way to do this today, but we have some potential workarounds.  If needed, in addition to a long-term solution.

### Cloud-init Workaround 1: Disable resource disk symlinks via udev rules

A udev rules file in `/etc` can be used to mask the cloud-init udev rules, preventing the symlink from being created:

```
ln -sf /dev/null /etc/udev/rules.d/66-azure-ephemeral.rules
```

Debugging shows this is well supported by systemd-udevd:

```
systemd-udevd[202]: Skipping overridden file '/usr/lib/udev/rules.d/66-azure-ephemeral.rules'.
systemd-udevd[202]: Skipping empty file: /etc/udev/rules.d/66-azure-ephemeral.rules
```

This is probably the simplest and most effective approach.

### Cloud-init Workaround 2: Redefining ephemeral0 => null

A config can be used to ensure cloud-init never partitions or formats the disk by redefining ephemeral0 such that it doesn't point to `/dev/disk/cloud/azure-resource`.

```yaml
datasource:
  Azure:
    disk_aliases:
      ephemeral0: null

mounts:
  - ["ephemeral0.1", null]
```

**Caveats:**

* this emits a warning when the device isn't found.

### Cloud-init Workaround 3: Re-configure cloud-init mount point

Cloud-init can be reconfigured to mount SCSI resource disk in non-conflicting path.

Example `/etc/cloud/cloud.cfg.d/99-azure-resource.cfg`:

```yaml
mounts:
   - ["ephemeral0.1", "/media/azure-scsi-resource"]
```

**Caveats:**

* Breaks scenario (b) when only SCSI resource disk is available.

### Long-term Plan: First-class Configuration in cloud-init

We will independently work on a toggle for cloud-init to disable SCSI resource disk handling and key off this in a future version.

Example:

```yaml
datasource:
  Azure:
    resoure_disk_setup: false
```

## Managing /etc/fstab

An entry will be added to `/etc/fstab`.

### fs_spec (source filesystem block device, uuid, etc.) 

This will depend on the case:

* aggregated units: `/dev/md/${AZURE_EPHEMERAL_DISK_SETUP_MDADM_NAME}_0`
* single local NVMe: `/dev/disk/azure/local/by-serial/<serial>`
* SCSI resource disk: `/dev/disk/azure/resource`

### fs_vfstype (filesystem type)

Matches `$AZURE_EPHEMERAL_DISK_SETUP_FS_TYPE`.

### fs_mntops (mount options)

Universal options: `defaults,nofail,comment=azure-ephemeral-disk-setup`

* `defaults` to get the default options.
* `nofail` to ensure lack of disk doesn't break boot process. 

  * This allows VM to boot properly when:

    * custom images contain artifacts from previous instance
    * VM is re-allocated/migrated
    * VM is migrated to new VM size, etc.

* `comment=azure-ephemeral-disk-setup` to signal that this service manages this line.

  * If there is any inconsistency in `/etc/fstab` lines with `comment=azure-ephemeral-disk-setup`, they will be deleted as part of setup.

### fs_freq (dump)

Always `0` (never dump).

### fs_passno (fsck)

Always `2` (check after root device).

### Example `/etc/fstab` Entry

```
/dev/md/azure-ephemeral-md_0  /mnt  xfs  defaults,nofail,comment=azure-ephemeral-disk-setup  0  2
```

### Avoiding Data Loss and Empty Disk Checks

If `/etc/fstab` does not contain an entry for the mount point, it is expected that the disks are empty.

But on re-allocation, etc. we may have to deal with fresh disks that aren't already formatted. To ensure we avoid data loss, we will take the following precautions:

* each local disk will be checked if in use with `findmnt <device>`

  * This service runs after `local-fs.target`, so these disks should be actively mounted if in use by another mechanism.

* `mdadm --create ...` and `mkfs.<fs_type>` will be invoked without `--force` flags to ensure they fail if the disks are partitioned/formatted or in-use

If any of these checks or tools fail, the failure will be reported and service will exit with failure.

In the worst case where these tools don't detect in-use disks due to unforseen conditions, the actual risk to a user is quite low as these disks are expected to be ephemeral and this process occcurs early enough in boot to avoid negatively impacting running services.

Given the limits on what we can reasonably detect, documentation will advise users not to opt-in to this service if using disks in a manner that would conflict and go undetected, e.g. doing direct block read/writes without a filesystem mounted.

**Caveats:**

The primary downside to these safety checks is that if the disk is in a bad state (e.g. reboot during formatting) it may be a bit tricky for the user to directly fix without some sort of `--force` option.  The safest, and easiest, guidance will be to re-allocate the VM if local disks are in a bad state.

## Future Work

* Consider LVM support for additional flexibility.

* Enhance cloud-init via a first-class toggle to disable default resource disk handling.