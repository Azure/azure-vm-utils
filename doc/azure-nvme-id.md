---
title: azure-nvme-id
section: 1
header: User Manual
footer: azure-nvme-id __VERSION__
date: __DATE__
---

# NAME

azure-nvme-id - Identify Azure NVMe devices.

# SYNOPSIS

**azure-nvme-id** [\-\-debug] [\-\-help | \-\-version | \-\-udev]

# DESCRIPTION

**azure-nvme-id** is a utility to identify Azure NVMe devices.

It performs an Identify Namespace command on the NVMe namespaces, parsing metadata available in the vendor-specific (vs) field which contains various identification details with a comma-separated, key=value format.

# OPTIONS

`--help`

:  Show usage information and exit.

`--version`

:  Show version information and exit.

`--udev`

:  Run in udev mode, printing a set of `<key>=<value>` variables consumed by udev rules.  Requires DEVNAME to be set in environment.

# EXAMPLES

Identify NVMe namespaces:

```bash
$ sudo azure-nvme-id
/dev/nvme0n1:
/dev/nvme1n1: type=local,index=1,name=nvme-110G-1
```

Parse device identifiers for udev consumption:

```bash
$ sudo env DEVNAME=/dev/nvme1n1 azure-nvme-id --udev
AZURE_DISK_VS=type=local,index=1,name=nvme-110G-1
AZURE_DISK_TYPE=local
AZURE_DISK_INDEX=1
AZURE_DISK_NAME=nvme-110G-1
```

Check `azure-nvme-id` version:

```bash
$ azure-nvme-id --version
azure-nvme-id 0.1.2
```

# SEE ALSO

Source and documentation available at: <https://github.com/Azure/azure-nvme-utils>
