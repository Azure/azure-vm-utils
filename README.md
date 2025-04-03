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

## 80-azure-disk.rules

Provides helpful symlinks in /dev/disk/azure for local, data, and os disks.

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

## test_images

To help automate a spread of tests, test_images provides functional testing for a set of pre-existing images,
assuming azure-vm-utils is already installed.  It depends on az-cli, ssh, and ssh-keygen to create VMs
and ssh into them to run the tests.

To run tests against marketplace and community images with azure-vm-utils:

```
SELFTEST_AZURE_SUBSCRIPTION=<subscription id> \
SELFTEST_AZURE_LOCATION=eastus2 \
pytest -v selftest
```

To run tests for custom images and vm sizes, the following variables are supported with comma-separated values:

- SELFTEST_ARM64_IMAGES
- SELFTEST_ARM64_VM_SIZES
- SELFTEST_GEN1_IMAGES
- SELFTEST_GEN1_VM_SIZES
- SELFTEST_GEN2_IMAGES
- SELFTEST_GEN2_VM_SIZES

For example:

```
SELFTEST_AZURE_SUBSCRIPTION=<subscription id> \
SELFTEST_AZURE_LOCATION=eastus2 \
SELFTEST_GEN2_IMAGES=/my/image1,/my/image2,... \
SELFTEST_GEN2_VM_SIZES=Standard_D2ds_v5,Standard_D2ds_v6,... \
pytest -xvvvs -k test_gen2
```

For convenience, the default spread of VM sizes is assumed if SELFTEST_{ARM64|GEN1|GEN2}_VM_SIZES is unset.
If unable to allocate VM, test is "skipped".

Supported environment variables:

- SELFTEST_ADMIN_USERNAME: admin name to configure VMs with
- SELFTEST_ADMIN_PASSWORD: optional password to enable easy serial-console access
- SELFTEST_ARTIFACTS_PATH: directory path to store artifacts under
- SELFTEST_AZURE_LOCATION: location to use
- SELFTEST_AZURE_SUBSCRIPTION: subscription to use
- SELFTEST_HOLD_FAILURES: skip cleanup for failures
- SELFTEST_REBOOTS: number of reboots to perform in test (default=50)
- SELFTEST_RESOURCE_GROUP: optional RG to use, otherwise one is created

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
