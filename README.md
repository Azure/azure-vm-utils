# azure-vm-utils

A collection of utilities and udev rules to make the most of the Linux experience on Azure.

## Quick Start

To build:

```
cmake .
make
```

To install:

```
sudo make install
```

# Executables

## azure-nvme-id

`azure-nvme-id` is a utility to help identify Azure NVMe devices.

To run:

```
sudo azure-nvme-id
```

To run in udev mode:

```
DEVNAME=/dev/nvme0n1 azure-nvme-id --udev
```

# Rules for udev

## 66-azure-storage.rules

Provides WALinuxAgent-compatible disk and partition symlinks:

```
/dev/disk/azure/root
/dev/disk/azure/root-part<partition>
/dev/disk/azure/resource
/dev/disk/azure/resource-part<partition>
/dev/disk/azure/scsi<controller>/lun<lun>
/dev/disk/azure/scsi<controller>/lun<lun>-part<partition>
```

Controllers range from 0 to 3. Controller 0 LUNs 0 and 1 use root and resource
instead; controller 0 LUN 2 (CD-ROM) is excluded.

Note that this purposely conflicts with WALinuxAgent udev rules
as it is an exact match.

## 80-azure-disk.rules

Provides disk and partition symlinks for OS, SCSI resource, data, and local NVMe disks:

```
/dev/disk/azure/data/by-lun/<lun>
/dev/disk/azure/data/by-lun/<lun>-part<partition>
/dev/disk/azure/local/by-index/<index>
/dev/disk/azure/local/by-index/<index>-part<partition>
/dev/disk/azure/local/by-name/<name>
/dev/disk/azure/local/by-name/<name>-part<partition>
/dev/disk/azure/local/by-serial/<serial>
/dev/disk/azure/local/by-serial/<serial>-part<partition>
/dev/disk/azure/os
/dev/disk/azure/os-part<partition>
/dev/disk/azure/resource
/dev/disk/azure/resource-part<partition>
```

## 99-azure-product-uuid.rules

Makes the SMBIOS product UUID readable by all local users (0444)
on Microsoft VMs, including Hyper-V, matching WALinuxAgent.

Note that this purposely conflicts with WALinuxAgent udev rules
as it is an exact match.

# Testing

## unit tests

There are unit test executables provided to validate functionality at build-time.
They are automatically enabled, but can be disabled with -DENABLE_TESTS=0 passed to cmake.

To build without tests:

```
mkdir build && cd build
cmake .. -DENABLE_TESTS=0
make
```

To build and execute tests:

```
mkdir build && cd build
cmake ..
make
ctest --output-on-failure
```

Optionally, ctest can be skipped in favor of running tests individually:

```
mkdir build && cd build
cmake ..
make
for test in *_tests; do ./$test; done
```

## selfcheck

selfcheck is provided to validate the runtime environment of a VM.

With azure-vm-utils installed in a VM on Azure, simply copy the selfcheck.py executable to the target and
execute with sudo.

```
scp selfcheck/selftest.py $ip: && ssh $ip -- sudo ./selftest.py
```

Selftest uses strict current-behavior checks by default. Use `--compat` to
allow for features not present in older distro-packaged versions.
Image tests enable compatibility for packaged utilities and keep strict
checks when installing from source.

## updating requirements

To refresh the frozen selftest dependency list from
[selftest/test-requirements.txt](selftest/test-requirements.txt), run:

```sh
./scripts/update-selftest-requirements.sh
```

This requires Docker and uses a Python 3.10 container to generate updated requirements.

## test_images

Image tests create Azure VMs from marketplace and community images and run
selftests over SSH. They require Azure CLI, `ssh`, and `ssh-keygen`.

Tests use utilities installed in each image. Set `SELFTEST_INSTALL_FROM_SOURCE=1`
to build and install from the working tree before testing.

See [test_images.py](selftest/test_images.py) for example runs, environment
variables, and the test matrix.

# Contributing

This project welcomes contributions and suggestions.  Most contributions require you to agree to a
Contributor License Agreement (CLA) declaring that you have the right to, and actually do, grant us
the rights to use your contribution. For details, visit https://cla.opensource.microsoft.com.

When you submit a pull request, a CLA bot will automatically determine whether you need to provide
a CLA and decorate the PR appropriately (e.g., status check, comment). Simply follow the instructions
provided by the bot. You will only need to do this once across all repos using our CLA.

This project has adopted the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/).
For more information see the [Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/) or
contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with any additional questions or comments.

## Trademarks

This project may contain trademarks or logos for projects, products, or services. Authorized use of Microsoft
trademarks or logos is subject to and must follow
[Microsoft's Trademark & Brand Guidelines](https://www.microsoft.com/en-us/legal/intellectualproperty/trademarks/usage/general).
Use of Microsoft trademarks or logos in modified versions of this project must not cause confusion or imply Microsoft sponsorship.
Any use of third-party trademarks or logos are subject to those third-party's policies.
