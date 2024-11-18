# Azure VM Utils - Disk Identification

## Introduction

azure-vm-utils is a new package to consolidate tools and udev rules which are critical to the Linux on Azure experience.

The initial focus for azure-vm-utils is to provide the tools and configuration to help the customer identify the various NVMe disk devices.

## Background

There are number of udev rules critical to the Linux on Azure experience, to assist managing devices including: SCSI, NVMe, MANA, Mellanox.
Today these rules are spread out among cloud-init, WALinuxAgent, azure-nvme-utils, and vendor-specific image customization.

### azure-nvme-utils

The precursor to azure-vm-utils, renamed to azure-vm-utils to support increased scope without requiring additional packages.

### WALinuxAgent

The WALinuxAgent team is working to decouple their guest agent from the provisioning agent.  The provisioning agent is being deprecated and will be removed in a future release.

The long-term plan is to migrate the udev rules and configuration found in WALinuxAgent into azure-vm-utils so they can be maintained and updated independently of the WALinuxAgent package.

Today, WALinuxAgent includes udev rules to provide several symlinks for SCSI disks, including:

- /dev/disk/azure/resource
- /dev/disk/azure/root
- /dev/disk/azure/scsi0/lun\<lun>
- /dev/disk/azure/scsi1/lun\<lun>

## Azure NVMe Controllers

Azure currently supports three NVMe disk controllers:

- MSFT NVMe Accelerator v1

  - Provides remote NVMe disks attached to the VM including OS and data disks.
  - All disks are currently found on one controller, future implementations may leverage multiple controllers.

- Microsoft NVMe Direct Disk v1

  - Earlist generation of VMs with directly-attached NVMe local disks, e.g. LSv2/LSv3.
  - Each local disk has its own controller.

- Microsoft NVMe Direct Disk v2

  - Second generation of NVMe directly-attached local disks used in v6 and newer VM sizes.
  - Each local disk has its own controller.

## NVMe Identify Namespace: Vendor-Specific Reserved

NVMe' identify namespace command returns a structure with a vendor-specific (VS) field found at offset 384 and is 3712 bytes long.

Azure utilizes this space to include some metadata about the device, including the disk's:

- type: specifies the type of NVMe device (os, data, local)

- index: indicates the specific device's index within a set, if applicable (local)

- lun: customer-configured "lun" for data disks

- name: customer-configured name for data disks, or designated name for local disks

The metadata is formatted as comma-separated key-value pairs truncated by a null-byte. Example VS metadata includes:

- type=local,index=1,name=nvme-300G-1\0
- type=os\0
- type=data,lun=4,name=data-db\0

If VS starts with a null-terminator, the protocol is unsupported.

This metadata is currently supported by Microsoft NVMe Direct Disk v2 and will be extended in the future.

## Disk Controller Identification For NVMe Disks without VS-based Identification

For NVMe devices which do not (yet) support identification via metadata in Identify Namespace, some identifiers
are derived from a combination of NVMe controller identifier and namespace identifier.

The following are assumed to be local disks:

- Microsoft NVMe Direct Disk v1
- Microsoft NVMe Direct Disk v2

The following is assumed to be OS disk:

- MSFT NVMe Accelerator v1, namespace id = 1

The following are assumed to be data disks:

- MSFT NVMe Accelerator v1, namespace id = 2+.  The "lun" for a data disk can be calculated by subtracting 2 from the namespace id.  This calculation may be different for Windows VMs.

## Disk Device Identification on Linux

The rules found in WALinuxAgent are being extended with azure-vm-utils to add identification support for NVMe devices.

New symlinks that will be provided for all instances with NVMe disks include:

- /dev/disk/azure/data/by-lun/\<lun>
- /dev/disk/azure/local/by-serial/\<serial>
- /dev/disk/azure/os

For v6 and newer VM sizes with local NVMe disks supporting namespace identifiers, additional links will be available:

- /dev/disk/azure/local/by-index/\<index>
- /dev/disk/azure/local/by-name/\<name>

For future VM sizes with remote NVMe disks supporting namespace identifiers, additional links will be available:

- /dev/disk/azure/data/by-name/\<name>

### SCSI Compatibility

For compatibility reasons, azure-vm-utils will ensure SCSI disks support the following links:

- /dev/disk/azure/os
- /dev/disk/azure/resource

Note that some VM sizes come with both NVMe "local" disks in addition to a SCSI "temp" resource disk.  These temp resource disks are considered to be separate from "local" disks which are dedicated to local NVMe disks to avoid confusion.

### Disk Identification Examples for Various VM Sizes & Configurations

#### Standard_D2s_v4 + 4 Data Disks

```bash
$ find /dev/disk/azure -type l | sort
/dev/disk/azure/data/by-lun/0
/dev/disk/azure/data/by-lun/1
/dev/disk/azure/data/by-lun/2
/dev/disk/azure/data/by-lun/3
/dev/disk/azure/os
/dev/disk/azure/os-part1
/dev/disk/azure/os-part14
/dev/disk/azure/os-part15
/dev/disk/azure/root
/dev/disk/azure/root-part1
/dev/disk/azure/root-part14
/dev/disk/azure/root-part15
/dev/disk/azure/scsi1/lun0
/dev/disk/azure/scsi1/lun1
/dev/disk/azure/scsi1/lun2
/dev/disk/azure/scsi1/lun3

$ sudo azure-nvme-id
<empty>
```

#### Standard_D2ds_v4 configured with 4 data disks

```bash
$ find /dev/disk/azure -type l | sort
/dev/disk/azure/data/by-lun/0
/dev/disk/azure/data/by-lun/1
/dev/disk/azure/data/by-lun/2
/dev/disk/azure/data/by-lun/3
/dev/disk/azure/os
/dev/disk/azure/os-part1
/dev/disk/azure/os-part14
/dev/disk/azure/os-part15
/dev/disk/azure/resource
/dev/disk/azure/resource-part1
/dev/disk/azure/root
/dev/disk/azure/root-part1
/dev/disk/azure/root-part14
/dev/disk/azure/root-part15
/dev/disk/azure/scsi1/lun0
/dev/disk/azure/scsi1/lun1
/dev/disk/azure/scsi1/lun2
/dev/disk/azure/scsi1/lun3

$ sudo azure-nvme-id
<empty>
```

#### Standard_E2bds_v5 configured with SCSI disk controller and 4 data disks

```bash
$ find /dev/disk/azure -type l | sort
/dev/disk/azure/data/by-lun/0
/dev/disk/azure/data/by-lun/1
/dev/disk/azure/data/by-lun/2
/dev/disk/azure/data/by-lun/3
/dev/disk/azure/os
/dev/disk/azure/os-part1
/dev/disk/azure/os-part14
/dev/disk/azure/os-part15
/dev/disk/azure/resource
/dev/disk/azure/resource-part1
/dev/disk/azure/root
/dev/disk/azure/root-part1
/dev/disk/azure/root-part14
/dev/disk/azure/root-part15
/dev/disk/azure/scsi1/lun0
/dev/disk/azure/scsi1/lun1
/dev/disk/azure/scsi1/lun2
/dev/disk/azure/scsi1/lun3

$ sudo azure-nvme-id
<empty>
```

#### Standard_E2bds_v5 configured with NVMe disk controller and 4 data disks

```bash
$ find /dev/disk/azure -type l | sort
/dev/disk/azure/data/by-lun/0
/dev/disk/azure/data/by-lun/1
/dev/disk/azure/data/by-lun/2
/dev/disk/azure/data/by-lun/3
/dev/disk/azure/os
/dev/disk/azure/os-part1
/dev/disk/azure/os-part14
/dev/disk/azure/os-part15
/dev/disk/azure/resource
/dev/disk/azure/resource-part1

$ sudo azure-nvme-id
/dev/nvme0n1:
/dev/nvme0n2:
/dev/nvme0n3:
/dev/nvme0n4:
/dev/nvme0n5:
```

#### Standard_E2bs_v5 configured with NVMe disk controller and 4 data disks

```bash
$ find /dev/disk/azure -type l | sort
/dev/disk/azure/data/by-lun/0
/dev/disk/azure/data/by-lun/1
/dev/disk/azure/data/by-lun/2
/dev/disk/azure/data/by-lun/3
/dev/disk/azure/os
/dev/disk/azure/os-part1
/dev/disk/azure/os-part14
/dev/disk/azure/os-part15

$ sudo azure-nvme-id
/dev/nvme0n1:
/dev/nvme0n2:
/dev/nvme0n3:
/dev/nvme0n4:
/dev/nvme0n5:
```

#### Standard_L8s_v3 configured with 4 data disks (1 local NVMe disk + 1 temp SCSI disk)

```bash
$ find /dev/disk/azure -type l | sort
/dev/disk/azure/data/by-lun/0
/dev/disk/azure/data/by-lun/1
/dev/disk/azure/data/by-lun/2
/dev/disk/azure/data/by-lun/3
/dev/disk/azure/local/by-serial/70307ea5392400000001
/dev/disk/azure/os
/dev/disk/azure/os-part1
/dev/disk/azure/os-part14
/dev/disk/azure/os-part15
/dev/disk/azure/resource
/dev/disk/azure/resource-part1
/dev/disk/azure/root
/dev/disk/azure/root-part1
/dev/disk/azure/root-part14
/dev/disk/azure/root-part15
/dev/disk/azure/scsi1/lun0
/dev/disk/azure/scsi1/lun1
/dev/disk/azure/scsi1/lun2
/dev/disk/azure/scsi1/lun3

$ sudo azure-nvme-id
/dev/nvme0n1:
```

#### Standard_L8s_v3 configured with 4 data disks (4 local NVMe disks + 1 temp SCSI disk)

```bash
$ find /dev/disk/azure -type l | sort
/dev/disk/azure/data/by-lun/0
/dev/disk/azure/data/by-lun/1
/dev/disk/azure/data/by-lun/2
/dev/disk/azure/data/by-lun/3
/dev/disk/azure/local/by-serial/f0451a1ba53a00000001
/dev/disk/azure/local/by-serial/f0451a1ba53a00000002
/dev/disk/azure/local/by-serial/f0451a1ba53a00000003
/dev/disk/azure/local/by-serial/f0451a1ba53a00000004
/dev/disk/azure/os
/dev/disk/azure/os-part1
/dev/disk/azure/os-part14
/dev/disk/azure/os-part15
/dev/disk/azure/resource
/dev/disk/azure/resource-part1
/dev/disk/azure/root
/dev/disk/azure/root-part1
/dev/disk/azure/root-part14
/dev/disk/azure/root-part15
/dev/disk/azure/scsi1/lun0
/dev/disk/azure/scsi1/lun1
/dev/disk/azure/scsi1/lun2
/dev/disk/azure/scsi1/lun3

$ sudo azure-nvme-id
/dev/nvme0n1:
/dev/nvme1n1:
/dev/nvme2n1:
/dev/nvme3n1:
```

#### Standard_D2alds_v6 configured with 2 data disks (1 local NVMe disk)

```bash
$ find /dev/disk/azure -type l | sort
/dev/disk/azure/data/by-lun/0
/dev/disk/azure/data/by-lun/1
/dev/disk/azure/local/by-index/1
/dev/disk/azure/local/by-name/nvme-440G-1
/dev/disk/azure/local/by-serial/ebeb91bd841bceb90001
/dev/disk/azure/os
/dev/disk/azure/os-part1
/dev/disk/azure/os-part14
/dev/disk/azure/os-part15

$ sudo azure-nvme-id
/dev/nvme0n1:
/dev/nvme0n2:
/dev/nvme0n3:
/dev/nvme1n1: type=local,index=1,name=nvme-110G-1
```

#### Standard_D16alds_v6 configured with 4 data disks (4 local NVMe disks)

```bash
$ find /dev/disk/azure -type l | sort
/dev/disk/azure/data/by-lun/0
/dev/disk/azure/data/by-lun/1
/dev/disk/azure/data/by-lun/2
/dev/disk/azure/data/by-lun/3
/dev/disk/azure/local/by-index/1
/dev/disk/azure/local/by-index/2
/dev/disk/azure/local/by-index/3
/dev/disk/azure/local/by-index/4
/dev/disk/azure/local/by-name/nvme-440G-1
/dev/disk/azure/local/by-name/nvme-440G-2
/dev/disk/azure/local/by-name/nvme-440G-3
/dev/disk/azure/local/by-name/nvme-440G-4
/dev/disk/azure/local/by-serial/351ea1d05ea261d50001
/dev/disk/azure/local/by-serial/351ea1d05ea261d50002
/dev/disk/azure/local/by-serial/351ea1d05ea261d50003
/dev/disk/azure/local/by-serial/351ea1d05ea261d50004
/dev/disk/azure/os
/dev/disk/azure/os-part1
/dev/disk/azure/os-part14
/dev/disk/azure/os-part15

$ sudo azure-nvme-id
/dev/nvme0n1:
/dev/nvme0n2:
/dev/nvme0n3:
/dev/nvme0n4:
/dev/nvme0n5:
/dev/nvme1n1: type=local,index=2,name=nvme-440G-2
/dev/nvme2n1: type=local,index=3,name=nvme-440G-3
/dev/nvme3n1: type=local,index=1,name=nvme-440G-1
/dev/nvme4n1: type=local,index=4,name=nvme-440G-4
```
