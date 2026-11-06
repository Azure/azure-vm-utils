---
title: azure-vm-utils-selftest
section: 8
header: User Manual
footer: azure-vm-utils-selftest __VERSION__
date: __DATE__
---

# NAME

azure-vm-utils-selftest - packaging self-tests

# SYNOPSIS

**azure-vm-utils-selftest [\-\-skip-imds-validation] [\-\-skip-udev-validation]**

# DESCRIPTION

**azure-vm-utils-selftest** validates functionailty related to azure-vm-utils package.

These self-tests validate azure\-nvme\-id outputs and /dev/disk/azure symlinks.
Legacy root, resource, SCSI controller/LUN and partition symlinks are checked
against the VMBus topology, regardless of which package installed the rules.
On matching Microsoft VMs, the SMBIOS product UUID must have mode 0444.
These checks are also enabled in compatibility mode and are skipped with
**\-\-skip-udev-validation**.

# EXAMPLES

Running self tests requires root:

```bash
$ sudo azure-vm-utils-selftest
```

To run inside Azure VM without a reboot after install:

```bash
azure-vm-utils-selftest --skip-udev-validation
```

To run outside of Azure VM:

```bash
azure-vm-utils-selftest --skip-imds-validation --skip-udev-validation
```

Hopefully it exits successfully!

# SEE ALSO

Source and documentation available at: <https://github.com/Azure/azure-vm-utils>
