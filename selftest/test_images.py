#!/usr/bin/env python3

# --------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.
# --------------------------------------------------------------------------

"""Azure VM utilities self-tests script."""

import os
import shlex
import subprocess
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

import pytest

from . import selftest

# pylint: disable=unknown-option-value
# pylint: disable=line-too-long
# pylint: disable=too-many-instance-attributes
# pylint: disable=too-many-arguments
# pylint: disable=too-many-positional-arguments
# pylint: disable=unused-argument
# pylint: disable=attribute-defined-outside-init
# pylint: disable=redefined-outer-name

DEFAULT_GEN1_VM_SIZES = [
    sku.vm_size
    for sku in selftest.SKU_CONFIGS.values()
    if sku.vm_size_type == "x64" and not sku.vm_size.endswith("v6")
]

DEFAULT_GEN2_VM_SIZES = [
    sku.vm_size for sku in selftest.SKU_CONFIGS.values() if sku.vm_size_type == "x64"
]

DEFAULT_ARM64_VM_SIZES = [
    sku.vm_size for sku in selftest.SKU_CONFIGS.values() if sku.vm_size_type == "arm64"
]

CUSTOM_IMAGES = [
    image for image in os.getenv("TEST_CUSTOM_IMAGES", "").split(",") if image
]
ENV_TEST_CUSTOM_VM_SIZES = os.getenv("TEST_CUSTOM_VM_SIZES", "")
if ENV_TEST_CUSTOM_VM_SIZES == "DEFAULT_GEN1_VM_SIZES":
    CUSTOM_VM_SIZES = DEFAULT_GEN1_VM_SIZES
elif ENV_TEST_CUSTOM_VM_SIZES == "DEFAULT_GEN2_VM_SIZES":
    CUSTOM_VM_SIZES = DEFAULT_GEN2_VM_SIZES
elif ENV_TEST_CUSTOM_VM_SIZES == "DEFAULT_ARM64_VM_SIZES":
    CUSTOM_VM_SIZES = DEFAULT_ARM64_VM_SIZES
else:
    CUSTOM_VM_SIZES = [image for image in ENV_TEST_CUSTOM_VM_SIZES.split(",") if image]


def subprocess_run(cmd: List[str], check: bool = True):
    """Run a subprocess command and capture outputs as utf-8."""
    print(f"executing command: {shlex.join(cmd)}")
    try:
        proc = subprocess.run(
            cmd,
            check=check,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except subprocess.CalledProcessError as error:
        print(
            f"error running command: {error} stdout={error.stdout} stderr={error.stderr}"
        )
        raise

    print(f"executed command: {proc}")
    return proc


@pytest.fixture
def ssh_key_path(tmp_path):
    """Generate a temporary SSH key pair for the test."""
    path = tmp_path / "id_rsa"
    subprocess.run(
        ["ssh-keygen", "-t", "rsa", "-b", "2048", "-f", str(path), "-N", ""], check=True
    )
    yield path


@pytest.fixture
def azure_subscription():
    """Get the Azure subscription ID."""
    subscription = os.getenv("AZURE_SUBSCRIPTION_ID") or ""
    assert subscription, "AZURE_SUBSCRIPTION_ID environment variable is required"
    yield subscription


@pytest.fixture
def azure_location():
    """Get the Azure location."""
    location = os.getenv("AZURE_LOCATION") or ""
    assert location, "AZURE_LOCATION environment variable is required"
    yield location


@pytest.fixture
def temp_resource_group(azure_subscription, azure_location):
    """Create a temporary resource group for the test."""
    resource_group_name = f"test-rg-{uuid.uuid4()}"
    delete_after = (datetime.utcnow() + timedelta(hours=1)).isoformat()
    subprocess.run(
        [
            "az",
            "group",
            "create",
            "--subscription",
            azure_subscription,
            "--location",
            azure_location,
            "--name",
            resource_group_name,
            "--tags",
            f"deleteAfter={delete_after}",
        ],
        check=True,
    )
    yield resource_group_name
    subprocess.run(
        ["az", "group", "delete", "--name", resource_group_name, "--yes", "--no-wait"],
        check=True,
    )


class TestVMs:
    """Test VMs with different images and sizes."""

    @pytest.fixture(autouse=True)
    def setup(
        self,
        azure_location,
        azure_subscription,
        ssh_key_path,
        temp_resource_group,
        image,
        vm_size,
    ):
        """Initialize the test."""
        self.admin_username = "azureuser"
        self.azure_location = azure_location
        self.azure_subscription = azure_subscription
        self.image = image
        self.selftest_script_path = (
            Path(os.path.abspath(__file__)).parent / "selftest.py"
        )
        self.ssh_key_path = ssh_key_path
        self.temp_resource_group = temp_resource_group
        self.vm_name = "test-vm"
        self.vm_size = vm_size

    def run_test(self) -> None:
        """Create VM and run self-tests."""
        target_script_path = f"/home/{self.admin_username}/selftest.py"

        # Create VM with 4 data disks
        proc = subprocess_run(
            [
                "az",
                "vm",
                "create",
                "--subscription",
                self.azure_subscription,
                "--resource-group",
                self.temp_resource_group,
                "--name",
                self.vm_name,
                "--image",
                self.image,
                "--size",
                self.vm_size,
                "--admin-username",
                self.admin_username,
                "--ssh-key-value",
                f"{self.ssh_key_path}.pub",
                "--data-disk-sizes-gb",
                "100",
                "200",
                "300",
                "400",
                "--accept-term",
            ],
            check=False,
        )

        if proc.returncode != 0:
            # Skip the test if the VM creation failed and indicate the reason.
            if "QuotaExceeded" in proc.stderr:
                pytest.skip(
                    f"Unable to create VM due to QuotaExceeded for {self.vm_size}: {proc.stderr}"
                )

            if "SkuNotAvailable" in proc.stderr:
                pytest.skip(
                    f"Unable to create VM due to SkuNotAvailable for {self.vm_size}: {proc.stderr}"
                )

            pytest.skip(
                f"Unable to create VM: stdout={proc.stdout} stderr={proc.stderr}"
            )

        # Get public IP address of the VM
        public_ip_address = None
        for _ in range(10):
            proc = subprocess_run(
                [
                    "az",
                    "vm",
                    "list-ip-addresses",
                    "--subscription",
                    self.azure_subscription,
                    "--resource-group",
                    self.temp_resource_group,
                    "--name",
                    self.vm_name,
                    "--query",
                    "[0].virtualMachine.network.publicIpAddresses[0].ipAddress",
                    "--output",
                    "tsv",
                ],
                check=False,
            )
            public_ip_address = proc.stdout.strip()
            if public_ip_address:
                break
            time.sleep(1)
        else:
            pytest.fail(
                f"Unable to get public IP address of the VM: stdout={proc.stdout} stderr={proc.stderr}"
            )

        ssh_command = [
            "ssh",
            "-i",
            self.ssh_key_path.as_posix(),
            f"{self.admin_username}@{public_ip_address}",
            "--",
            "sudo",
        ]

        # Wait for the VM to be ready
        status = "unknown"
        while status not in ("running", "degraded"):
            proc = subprocess_run(
                ssh_command + ["cloud-init", "status", "--wait"], check=False
            )
            proc = subprocess_run(
                ssh_command + ["systemctl", "is-system-running", "--wait"], check=False
            )
            status = proc.stdout.strip()

        subprocess_run(
            ssh_command + ["journalctl", "-o", "short-monotonic"], check=False
        )
        subprocess_run(
            [
                "scp",
                "-i",
                self.ssh_key_path.as_posix(),
                self.selftest_script_path.as_posix(),
                f"{self.admin_username}@{public_ip_address}:{target_script_path}",
            ],
        )
        subprocess_run(ssh_command + [target_script_path, "--debug"], check=True)

    @pytest.mark.parametrize(
        "image",
        [
            "debian:debian-13-daily:13:latest",
            "debian:debian-sid-daily:sid:latest",
        ],
    )
    @pytest.mark.parametrize(
        "vm_size",
        DEFAULT_GEN1_VM_SIZES,
    )
    def test_gen1_x64(self, image, vm_size):
        """Test gen1 x64 images."""
        self.run_test()

    @pytest.mark.parametrize(
        "image",
        [
            "debian:debian-13-daily:13-gen2:latest",
            "debian:debian-sid-daily:sid-gen2:latest",
            "/CommunityGalleries/Fedora-5e266ba4-2250-406d-adad-5d73860d958f/Images/Fedora-Cloud-Rawhide-x64/versions/latest",
        ],
    )
    @pytest.mark.parametrize(
        "vm_size",
        DEFAULT_GEN2_VM_SIZES,
    )
    def test_gen2_x64(self, image, vm_size):
        """Test gen2 x64 images."""
        self.run_test()

    @pytest.mark.parametrize(
        "image",
        [
            "debian:debian-13-daily:13-arm64:latest",
            "debian:debian-sid-daily:sid-arm64:latest",
            "/CommunityGalleries/Fedora-5e266ba4-2250-406d-adad-5d73860d958f/Images/Fedora-Cloud-Rawhide-Arm64/versions/latest",
        ],
    )
    @pytest.mark.parametrize(
        "vm_size",
        DEFAULT_ARM64_VM_SIZES,
    )
    def test_arm64(self, image, vm_size):
        """Test arm64 images."""
        self.run_test()

    @pytest.mark.parametrize(
        "image",
        CUSTOM_IMAGES,
    )
    @pytest.mark.parametrize(
        "vm_size",
        CUSTOM_VM_SIZES,
    )
    def test_custom(self, image, vm_size):
        """Test custom images."""
        self.run_test()
