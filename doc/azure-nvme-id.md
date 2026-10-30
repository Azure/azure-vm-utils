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
type, name, index, etc.

Diagnostics, including underlying system errors, are written to stderr.

# DEVICE ENUMERATION

Without `--udev`, **azure-nvme-id** enumerates Microsoft NVMe controllers
under `/sys/class/nvme` and identifies their namespaces. Output options are
plain or json.

JSON output includes `path`, `nsid`, `model`, `properties`, and `vs` for each namespace.

These errors are reported to stderr but do not stop enumeration:

* Missing `/sys/class/nvme` means no controllers. A missing controller
  directory means no namespaces for that controller.
* An unreadable `device/vendor` or `model` file, or an invalid vendor ID,
  skips the controller.
* A failed model reread during fallback identification leaves properties empty.
* `lun` or `index` values that cannot be converted to integers stay strings
  in JSON output.

Exit status `0` does not guarantee that every device was identified.

# UDEV DEVICE IDENTIFICATION

The `--udev` option identifies a single NVMe namespace device specified by
the required `DEVNAME` environment variable instead of enumerating controllers.
It queries that device directly, without sysfs vendor filtering or model-based
fallback identification.

Output is a set of `<key>=<value>` variables for consumption by udev rules.
`AZURE_DISK_VS` contains the vendor-specific data. Each property in that data
is also printed with its key converted to uppercase and prefixed with
`AZURE_DISK_`, such as `AZURE_DISK_TYPE`, `AZURE_DISK_INDEX`, and
`AZURE_DISK_NAME`.

# OPTIONS

`--debug`

: Debug mode with additional logging.

`--format {plain|json}`

: Output format, default is plain.

`--help`

:  Show usage information and exit.

`--udev`

: Run in udev mode. See UDEV DEVICE IDENTIFICATION.

`--version`

:  Show version information and exit.

# EXIT STATUS

`0`

: Success, including `--help`, `--version`, or finding no matching devices.

`1`

: Invalid command-line arguments.

`2`

: Failure to scan `/sys/class/nvme`, except for `ENOENT`, which is treated
  as success.

`3`

: Failure to scan `/sys/class/nvme/<controller>` for namespaces, except for
  `ENOENT`, which is treated as success.

`4`

: Memory allocation failure in namespace identification, udev property
  processing, or JSON processing, including JSON construction and serialization.

`5`

: Failure to open an NVMe namespace device, either to obtain its namespace
  ID or to execute Identify Namespace.

`6`

: An ioctl error executing the NVMe Identify Namespace command.

`7`

: The NVMe Identify Namespace command returned a nonzero NVMe completion
  status. The status is printed in hexadecimal on stderr; it is not used
  directly as the process exit status.

`8`

: An ioctl error obtaining a namespace ID with `NVME_IOCTL_ID`.

`9`

: Failure to obtain the page size with `sysconf()` for Identify Namespace.

`10`

: Malformed vendor-specific key-value properties in udev mode.

`11`

: The `DEVNAME` environment variable is not set in udev mode.

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
