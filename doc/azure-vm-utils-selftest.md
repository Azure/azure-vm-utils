---
title: azure-vm-utils-selftest
section: 8
header: User Manual
footer: azure-vm-utils-selftest __VERSION__
date: __DATE__
---

# NAME

azure-vm-utils-selftest - Self-tests for azure-vm-utils package.

# SYNOPSIS

**azure-vm-utils-selftest** [--skip-imds-validation] [--skip-symlink-validation]

# DESCRIPTION

**azure-vm-utils-selftest** is a utility to identify Azure NVMe devices.

These self-tests validate azure\-nvme\-id outputs and /dev/disk/azure symlinks.

# EXAMPLES

Running self tests requires root:

```bash
$ sudo azure-vm-utils-selftest
```

To run inside Azure VM without a reboot after install:

```bash
azure-vm-utils-selftest --skip-symlink-validation
```

To run outside of Azure VM:

```bash
azure-vm-utils-selftest --skip-imds-validation --skip-symlink-validation
```

Hopefully it exits successfully!

# SEE ALSO

Source and documentation available at: <https://github.com/Azure/azure-vm-utils>
