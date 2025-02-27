---
title: azure-nvme-id
section: 8
header: User Manual
footer: azure-nvme-id __VERSION__
date: __DATE__
---

# NAME

azure-nvme-id - identify Azure NVMe devices

# SYNOPSIS

**azure-nvme-id** [\-\-debug] [\-\-format {plain|json}] [\-\-help | \-\-version | \-\-udev]

# DESCRIPTION

**azure-nvme-id** provides identification metadata in the response to Identify Namespace command for some models of NVMe devices.
This is found in vendor-specific (vs) field which contains various identification details with a comma-separated, key=value format.

**azure-nvme-id** combines this metadata with the make and model of NVMe device namespaces to identify a device by
type, name, index, etc. Output options are plain or json.

To suppoort udev rules, \-\-udev option will invoke **azure-nvme-id** in udev mode.

# OPTIONS

`--debug`

: Debug mode with additional logging.

`--format {plain|json}`

: Output format, default is plain.

`--help`

:  Show usage information and exit.

`--udev`

:  Run in udev mode, printing a set of `<key>=<value>` variables consumed by udev rules.  Requires DEVNAME to be set in environment.

`--version`

:  Show version information and exit.

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

Source and documentation available at: <https://github.com/Azure/azure-vm-utils>
