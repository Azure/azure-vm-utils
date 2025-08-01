#!/usr/bin/env python3

# --------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.
# --------------------------------------------------------------------------

"""Azure VM utilities self-tests script."""

import codecs
import getpass
import logging
import os
import shlex
import subprocess
import time
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List

import pytest

from . import selftest

logger = logging.getLogger(__name__)

# pylint: disable=unknown-option-value
# pylint: disable=line-too-long
# pylint: disable=too-many-instance-attributes
# pylint: disable=too-many-arguments
# pylint: disable=too-many-lines
# pylint: disable=too-many-locals
# pylint: disable=too-many-positional-arguments
# pylint: disable=unused-argument
# pylint: disable=attribute-defined-outside-init
# pylint: disable=redefined-outer-name

ARM64_IMAGES = [
    image for image in os.getenv("SELFTEST_ARM64_IMAGES", "").split(",") if image
]
if not ARM64_IMAGES:
    ARM64_IMAGES = [
        "debian:debian-13-daily:13-arm64:latest",
        "debian:debian-sid-daily:sid-arm64:latest",
        "/CommunityGalleries/Fedora-5e266ba4-2250-406d-adad-5d73860d958f/Images/Fedora-Cloud-Rawhide-Arm64/versions/latest",
    ]
ARM64_VM_SIZES = [
    vm_size
    for vm_size in os.getenv("SELFTEST_ARM64_VM_SIZES", "").split(",")
    if vm_size
]
if not ARM64_VM_SIZES:
    ARM64_VM_SIZES = [
        sku.vm_size
        for sku in selftest.SKU_CONFIGS.values()
        if sku.vm_size_type == "arm64"
    ]

GEN1_IMAGES = [
    image for image in os.getenv("SELFTEST_GEN1_IMAGES", "").split(",") if image
]
if not GEN1_IMAGES:
    GEN1_IMAGES = [
        "debian:debian-13-daily:13:latest",
        "debian:debian-sid-daily:sid:latest",
    ]
GEN1_VM_SIZES = [
    vm_size for vm_size in os.getenv("SELFTEST_GEN1_VM_SIZES", "").split(",") if vm_size
]
if not GEN1_VM_SIZES:
    GEN1_VM_SIZES = [
        sku.vm_size
        for sku in selftest.SKU_CONFIGS.values()
        if sku.vm_size_type == "x64" and not sku.vm_size.endswith("v6")
    ]

GEN2_IMAGES = [
    image for image in os.getenv("SELFTEST_GEN2_IMAGES", "").split(",") if image
]
if not GEN2_IMAGES:
    GEN2_IMAGES = [
        "debian:debian-13-daily:13-gen2:latest",
        "debian:debian-sid-daily:sid-gen2:latest",
        "/CommunityGalleries/Fedora-5e266ba4-2250-406d-adad-5d73860d958f/Images/Fedora-Cloud-Rawhide-x64/versions/latest",
    ]
GEN2_VM_SIZES = [
    vm_size for vm_size in os.getenv("SELFTEST_GEN2_VM_SIZES", "").split(",") if vm_size
]
if not GEN2_VM_SIZES:
    GEN2_VM_SIZES = [
        sku.vm_size
        for sku in selftest.SKU_CONFIGS.values()
        if sku.vm_size_type == "x64"
    ]


def safe_parse_bytes_literal(s: str) -> str:
    """Parse a bytes literal string (e.g. b'foo') safely to a string (foo)."""
    s = s.strip()
    if not s.startswith("b'") or not s.endswith("'"):
        return s

    # Strip the b' and trailing '
    inner = s[2:-1]
    # Decode escape sequences (e.g., \r, \n, \x00)
    raw_bytes: bytes = codecs.escape_decode(inner.encode())[0]  # type: ignore
    return raw_bytes.decode("utf-8", errors="ignore").rstrip("\x00")


def _subprocess_run(
    cmd: List[str],
    *,
    artifacts_path: Path,
    artifact_name: str,
    check: bool = False,
    decode: bool = False,
) -> subprocess.CompletedProcess:
    """Run a subprocess command and capture outputs as utf-8."""
    artifact_path = artifacts_path / artifact_name
    printable_cmd = shlex.join(cmd)

    logger.debug("executing command: %s", printable_cmd)
    proc = subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    logger.debug(
        "executed command=%s rc=%d artifact=%s",
        printable_cmd,
        proc.returncode,
        artifact_path.as_posix(),
    )

    stdout = proc.stdout
    stderr = proc.stderr
    if decode:
        # Decode potential byte repr strings from get-boot-log.
        stdout = safe_parse_bytes_literal(stdout)
        stderr = safe_parse_bytes_literal(stderr)

    artifact_path.write_text(
        f"cmd: {printable_cmd}\nrc: {proc.returncode}\nstdout:\n{stdout!s}\nstderr:\n{stderr!s}",
        encoding="utf-8",
    )

    if proc.returncode != 0:
        logger.error(
            "command failed: %s rc=%d artifact=%s\nstdout:\n%s\nstderr:\n%s",
            printable_cmd,
            proc.returncode,
            artifact_path.as_posix(),
            stdout,
            stderr,
        )

    if check and proc.returncode != 0:
        raise RuntimeError(
            f"Command '{printable_cmd}' failed with return code {proc.returncode}: {artifact_path.as_posix()}\nstdout={stdout!s}\nstderr={stderr!s}"
        )

    return proc


@pytest.fixture
def artifacts_path(tmp_path, vm_size, image, temp_vm_name):
    """Generate a temporary SSH key pair for the test."""
    artifacts_path = os.getenv("SELFTEST_ARTIFACTS_PATH")
    if artifacts_path:
        tmp_path = Path(artifacts_path)

    path = tmp_path / vm_size / image.replace("/", "_").replace(":", "_") / temp_vm_name
    path.mkdir(exist_ok=True, parents=True)
    yield path


@pytest.fixture
def ssh_key_path(artifacts_path):
    """Generate a temporary SSH key pair for the test."""
    path = artifacts_path / "id_rsa"
    _subprocess_run(
        ["ssh-keygen", "-t", "rsa", "-b", "2048", "-f", str(path), "-N", ""],
        artifact_name="ssh-keygen",
        artifacts_path=artifacts_path,
        check=True,
    )

    yield path


@pytest.fixture
def azure_subscription():
    """Get the Azure subscription ID."""
    subscription = os.getenv("SELFTEST_AZURE_SUBSCRIPTION") or ""
    assert subscription, "SELFTEST_AZURE_SUBSCRIPTION environment variable is required"
    yield subscription


@pytest.fixture
def azure_location():
    """Get the Azure location."""
    location = os.getenv("SELFTEST_AZURE_LOCATION")
    assert location, "SELFTEST_AZURE_LOCATION environment variable is required"
    yield location


@pytest.fixture
def admin_username():
    """Get the admin username."""
    username = os.getenv("SELFTEST_ADMIN_USERNAME", "azureuser")
    yield username


@pytest.fixture
def admin_password():
    """Get the admin password."""
    yield os.getenv("SELFTEST_ADMIN_PASSWORD")


@pytest.fixture
def hold_failures():
    """Get the hold failures flag."""
    yield bool(os.getenv("SELFTEST_HOLD_FAILURES"))


@pytest.fixture
def random_suffix():
    """Generate a random suffix for the resource group."""
    yield str(uuid.uuid4().hex[:8])


@pytest.fixture
def reallocates():
    """Get the number of reallocates."""
    yield int(os.getenv("SELFTEST_REALLOCATES", "5"))


@pytest.fixture
def reboots():
    """Get the number of reboots."""
    yield int(os.getenv("SELFTEST_REBOOTS", "5"))


@pytest.fixture
def temp_vm_name(random_suffix):
    """Create a temporary resource group for the test."""
    user = getpass.getuser()
    yield f"temp-vm-{user}-selftest-{random_suffix}"


def is_cleanup_permitted(request, hold_failures: bool = False) -> bool:
    """Check to see if resources should be deleted."""
    aborted = getattr(request.session, "aborted", False)
    failed = getattr(request.session, "failed", False)

    logger.debug(
        "test session aborted=%s failed=%s hold_failures=%s",
        aborted,
        failed,
        hold_failures,
    )

    if hold_failures and failed:
        return False
    return True


@pytest.fixture
def temp_resource_group(
    azure_subscription,
    azure_location,
    delete_after_tag,
    hold_failures,
    random_suffix,
    request,
    artifacts_path,
):
    """Create a temporary resource group for the test."""
    create_rg = True
    env_rg = os.getenv("SELFTEST_RESOURCE_GROUP")
    if env_rg:
        resource_group_name = env_rg
        proc = _subprocess_run(
            [
                "az",
                "group",
                "show",
                "--subscription",
                azure_subscription,
                "--name",
                resource_group_name,
            ],
            artifact_name="az_group_show",
            artifacts_path=artifacts_path,
        )

        if proc.returncode == 0:
            create_rg = False
    else:
        user = getpass.getuser()
        resource_group_name = f"temp-rg-{user}-selftest-{random_suffix}"

    nsg_name = f"{resource_group_name}-nsg"
    subnet_name = f"{resource_group_name}-subnet"
    vnet_name = f"{resource_group_name}-vnet"

    if create_rg:
        _subprocess_run(
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
                f"deleteAfter={delete_after_tag}",
            ],
            artifact_name="az_group_create",
            artifacts_path=artifacts_path,
            check=True,
        )
        logger.info("created resource group: %s", resource_group_name)

        proc = _subprocess_run(
            [
                "az",
                "network",
                "nsg",
                "create",
                "--subscription",
                azure_subscription,
                "--resource-group",
                resource_group_name,
                "--location",
                azure_location,
                "--name",
                nsg_name,
            ],
            artifact_name="az_network_nsg_create",
            artifacts_path=artifacts_path,
            check=False,
        )
        if (
            proc.returncode != 0
            and "CanceledAndSupersededDueToAnotherOperation" not in proc.stderr
        ):
            raise RuntimeError(
                f"Failed to create NSG {nsg_name} in resource group {resource_group_name}: stdout={proc.stdout} stderr={proc.stderr}"
            )

        logger.info("created nsg: %s", proc.stdout.strip())

        proc = _subprocess_run(
            [
                "az",
                "network",
                "nsg",
                "rule",
                "create",
                "--subscription",
                azure_subscription,
                "--resource-group",
                resource_group_name,
                "--nsg-name",
                nsg_name,
                "--name",
                "DefaultAllowSSH",
                "--priority",
                "1000",
                "--protocol",
                "Tcp",
                "--destination-port-range",
                "22",
                "--access",
                "Allow",
            ],
            artifact_name="az_network_nsg_rule_ssh_create",
            artifacts_path=artifacts_path,
            check=False,
        )
        if (
            proc.returncode != 0
            and "CanceledAndSupersededDueToAnotherOperation" not in proc.stderr
        ):
            raise RuntimeError(
                f"Failed to create NSG rule DefaultAllowSSH in resource group {resource_group_name}: stdout={proc.stdout} stderr={proc.stderr}"
            )

        logger.info("created nsg rule: %s", proc.stdout.strip())

        proc = _subprocess_run(
            [
                "az",
                "network",
                "vnet",
                "create",
                "--subscription",
                azure_subscription,
                "--resource-group",
                resource_group_name,
                "--location",
                azure_location,
                "--name",
                vnet_name,
                "--address-prefix",
                "10.0.0.0/16",
            ],
            artifact_name="az_network_vnet_create",
            artifacts_path=artifacts_path,
            check=True,
        )
        logger.info("created vnet: %s", proc.stdout.strip())

        proc = _subprocess_run(
            [
                "az",
                "network",
                "vnet",
                "subnet",
                "create",
                "--subscription",
                azure_subscription,
                "--resource-group",
                resource_group_name,
                "--vnet-name",
                vnet_name,
                "--name",
                subnet_name,
                "--address-prefix",
                "10.0.1.0/24",
                "--network-security-group",
                nsg_name,
                "--default-outbound-access",
                "false",
            ],
            artifact_name="az_network_vnet_subnet_create",
            artifacts_path=artifacts_path,
            check=True,
        )
        logger.info("created subnet: %s", proc.stdout.strip())

    yield resource_group_name

    if not env_rg and is_cleanup_permitted(request, hold_failures):
        _subprocess_run(
            [
                "az",
                "group",
                "delete",
                "--name",
                resource_group_name,
                "--yes",
                "--no-wait",
            ],
            artifact_name="az_group_delete",
            artifacts_path=artifacts_path,
            check=True,
        )


@pytest.fixture
def public_ip(
    temp_resource_group,
    azure_subscription,
    azure_location,
    hold_failures,
    random_suffix,
    request,
    artifacts_path,
):
    """Create a temporary public IP address for the test."""
    while True:
        ip_name = f"temp-ip-{random_suffix}"
        public_ip_create_cmd = [
            "az",
            "network",
            "public-ip",
            "create",
            "--subscription",
            azure_subscription,
            "--resource-group",
            temp_resource_group,
            "--location",
            azure_location,
            "--name",
            ip_name,
            "--sku",
            "Standard",
            "--allocation-method",
            "Static",
            "--query",
            "publicIp.ipAddress",
            "--output",
            "tsv",
        ]

        ip_tags = os.getenv("SELFTEST_PUBLIC_IP_TAGS", "")
        if ip_tags:
            public_ip_create_cmd += ["--ip-tags", ip_tags]

        proc = _subprocess_run(
            public_ip_create_cmd,
            artifact_name="az_public_ip_create",
            artifacts_path=artifacts_path,
            check=True,
        )

        public_ip = proc.stdout.strip()

        delete_cmd = [
            "az",
            "network",
            "public-ip",
            "delete",
            "--subscription",
            azure_subscription,
            "--resource-group",
            temp_resource_group,
            "--name",
            ip_name,
        ]

        # Temporary workaround for VPN-unroutable networks.
        if any(
            public_ip.startswith(prefix) for prefix in ("20.242", "68.154.", "128.24.")
        ):
            _subprocess_run(
                delete_cmd,
                check=True,
                artifacts_path=artifacts_path,
                artifact_name="az_public_ip_delete",
            )
            continue

        yield public_ip, ip_name

        if is_cleanup_permitted(request, hold_failures):
            for _ in range(30):
                # Some retries to delete the public IP may be required.
                proc = _subprocess_run(
                    delete_cmd,
                    check=False,
                    artifacts_path=artifacts_path,
                    artifact_name="az_public_ip_delete",
                )
                if proc.returncode == 0:
                    break

                time.sleep(2)

        return


@pytest.fixture
def delete_after_tag():
    """Get the deleteAfter tag value."""
    yield (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()


class TestVMs:
    """Test VMs with different images and sizes."""

    @pytest.fixture(autouse=True)
    def setup(
        self,
        admin_username,
        admin_password,
        azure_location,
        azure_subscription,
        artifacts_path,
        delete_after_tag,
        hold_failures,
        public_ip,
        reallocates,
        reboots,
        request,
        ssh_key_path,
        temp_resource_group,
        temp_vm_name,
        image,
        vm_size,
    ):
        """Initialize the test."""
        self.admin_username = admin_username
        self.admin_password = admin_password
        self.artifacts_path = artifacts_path
        self.azure_location = azure_location
        self.azure_subscription = azure_subscription
        self.alloc = 0
        self.boot = 0
        self.delete_after_tag = delete_after_tag
        self.hold_failures = hold_failures
        self.image = image
        self.public_ip, self.public_ip_name = public_ip
        self.reallocates = reallocates
        self.reboots = reboots
        self.request = request
        self.selftest_script_path = (
            Path(os.path.abspath(__file__)).parent / "selftest.py"
        )
        self.ssh_key_path = ssh_key_path
        self.target_script_path = f"/home/{self.admin_username}/selftest.py"
        self.temp_resource_group = temp_resource_group
        self.vm_name = temp_vm_name
        self.vm_size = vm_size
        self.nsg_name = f"{temp_resource_group}-nsg"
        self.subnet_name = f"{temp_resource_group}-subnet"
        self.vnet_name = f"{temp_resource_group}-vnet"

        self.ssh_command = [
            "ssh",
            "-i",
            self.ssh_key_path.as_posix(),
            "-o",
            "StrictHostKeyChecking=no",
            f"{self.admin_username}@{self.public_ip}",
            "--",
            "sudo",
        ]
        self.vm_cfg = (
            f"name={self.vm_name}\n"
            f"rg={self.temp_resource_group}\n"
            f"ip={self.public_ip}\n"
            f"image={self.image}\n"
            f"size={self.vm_size}\n"
            f"ssh_key_path={self.ssh_key_path.as_posix()}\n"
            f'ssh_cmd="{shlex.join(self.ssh_command)}"\n'
            f'console_cmd="az serial-console connect -n {self.vm_name} -g {self.temp_resource_group}"\n'
            f"artifacts_path={self.artifacts_path.as_posix()}\n"
        )

        # Ensure the failed flag is reset for each test run as it is used
        request.session.failed = False

        try:
            yield
        finally:
            if is_cleanup_permitted(request, hold_failures):
                logger.info("cleaning:\n%s", self.vm_cfg)
                self._cleanup()
            else:
                logger.error(
                    "TEST FAILED, HOLDING RESOURCES FOR DEBUGGING:\n%s",
                    self.vm_cfg,
                )

    @property
    def boot_id(self) -> str:
        """Generate a boot ID based on the alloc and boot counts."""
        return f"alloc{self.alloc}-boot{self.boot}"

    def _cleanup(self):
        """Cleanup resources."""
        proc = _subprocess_run(
            [
                "az",
                "vm",
                "delete",
                "--subscription",
                self.azure_subscription,
                "--resource-group",
                self.temp_resource_group,
                "--name",
                self.vm_name,
                "--yes",
            ],
            artifacts_path=self.artifacts_path,
            artifact_name="az_vm_delete",
        )
        if proc.returncode != 0:
            logger.error("failed to delete VM %s: %s", self.vm_name, proc.stderr)

    def _create_vm(self) -> None:
        """Create a VM."""
        cmd = [
            "az",
            "vm",
            "create",
            "--subscription",
            self.azure_subscription,
            "--resource-group",
            self.temp_resource_group,
            "--location",
            self.azure_location,
            "--name",
            self.vm_name,
            "--image",
            self.image,
            "--size",
            self.vm_size,
            "--public-ip-address",
            self.public_ip_name,
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
            "--data-disk-delete-option",
            "Delete",
            "--nic-delete-option",
            "Delete",
            "--os-disk-delete-option",
            "Delete",
            "--tags",
            f"deleteAfter={self.delete_after_tag}",
            "--nsg",
            self.nsg_name,
            "--subnet",
            self.subnet_name,
            "--vnet-name",
            self.vnet_name,
        ]

        if self.admin_password:
            cmd += ["--admin-password", self.admin_password]

        proc = _subprocess_run(
            cmd,
            artifacts_path=self.artifacts_path,
            artifact_name="az_vm_create",
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

        logger.info("created VM:\n%s", self.vm_cfg)
        (self.artifacts_path / "vm.cfg").write_text(self.vm_cfg)

        # Enable boot diagnostics
        proc = _subprocess_run(
            [
                "az",
                "vm",
                "boot-diagnostics",
                "enable",
                "--subscription",
                self.azure_subscription,
                "--resource-group",
                self.temp_resource_group,
                "--name",
                self.vm_name,
            ],
            artifacts_path=self.artifacts_path,
            artifact_name="az_vm_boot_diagnostics_enable",
        )

    def _execute_ssh_command(
        self, command: List[str], *, artifact_name: str, decode: bool = False
    ) -> subprocess.CompletedProcess:
        """Execute a command on the VM with sudo."""
        proc = _subprocess_run(
            self.ssh_command + command,
            artifacts_path=self.artifacts_path,
            artifact_name=artifact_name,
            decode=decode,
        )
        return proc

    def _fetch_boot_diagnostics(self) -> None:
        """Fetch boot diagnostics logs."""
        for _ in range(300):
            proc = _subprocess_run(
                [
                    "az",
                    "vm",
                    "boot-diagnostics",
                    "get-boot-log",
                    "--subscription",
                    self.azure_subscription,
                    "--resource-group",
                    self.temp_resource_group,
                    "--name",
                    self.vm_name,
                    "--output",
                    "tsv",
                ],
                artifacts_path=self.artifacts_path,
                artifact_name=f"{self.boot_id}-console",
                decode=True,
            )
            if proc.returncode == 0 and "BlobNotFound" not in proc.stderr:
                return

            time.sleep(1)

    def _fetch_logs(self) -> None:
        """Fetch logs."""
        proc = self._execute_ssh_command(
            ["journalctl", "-o", "short-monotonic", "-b"],
            artifact_name=f"{self.boot_id}-journal",
        )

        if proc.returncode != 0:
            raise RuntimeError(
                f"failed to fetch journalctl logs on {self.boot_id} @ {self.artifacts_path.as_posix()}: {proc.stderr}"
            )

        self._scp_from_vm("/var/log/cloud-init.log", f"{self.boot_id}-cloud-init.log")
        self._scp_from_vm(
            "/var/log/cloud-init-output.log", f"{self.boot_id}-cloud-init-output.log"
        )
        self._execute_ssh_command(
            ["rm", "-f", "/var/log/cloud-init.log", "/var/log/cloud-init-output.log"],
            artifact_name=f"{self.boot_id}-rm-logs",
        )

    def _run_selftest_script(self) -> None:
        """Run selftest script on the VM."""
        proc = self._execute_ssh_command(
            [self.target_script_path, "--debug"],
            artifact_name=f"{self.boot_id}-selftest",
        )

        if proc.returncode != 0:
            raise RuntimeError(
                f"self-test failed on {self.boot_id} @ {self.artifacts_path.as_posix()}: {proc.stderr}"
            )

    def _scp_from_vm(self, src: str, artifact_name: str) -> Path:
        """Copy file from the VM using ssh with sudo."""
        dst = self.artifacts_path / artifact_name
        proc = self._execute_ssh_command(
            ["cat", src], artifact_name=f"{artifact_name}.cmd"
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"failed to copy {src} -> {dst.as_posix()}: {proc.stderr}"
            )

        dst.write_text(proc.stdout, encoding="utf-8")
        return dst

    def _scp_to_vm(self, src: Path, dst: str) -> None:
        """Copy file to VM."""
        src_path = src.as_posix()
        dst = f"{self.admin_username}@{self.public_ip}:{dst}"
        proc = _subprocess_run(
            [
                "scp",
                "-i",
                self.ssh_key_path.as_posix(),
                src_path,
                dst,
            ],
            artifacts_path=self.artifacts_path,
            artifact_name=f"scp-{src.name}",
        )
        if proc.returncode != 0:
            raise RuntimeError(f"failed to scp {src_path} -> {dst}: {proc.stderr}")

    def _deallocate_vm(self) -> None:
        """Deallocate the VM."""
        proc = _subprocess_run(
            [
                "az",
                "vm",
                "deallocate",
                "--subscription",
                self.azure_subscription,
                "--resource-group",
                self.temp_resource_group,
                "--name",
                self.vm_name,
            ],
            artifacts_path=self.artifacts_path,
            artifact_name="az_vm_deallocate",
        )
        if proc.returncode != 0:
            raise RuntimeError(f"failed to deallocate VM {self.vm_name}: {proc.stderr}")

        logger.info("deallocated VM: %s", self.vm_name)

    def _get_vm_powerstate(self) -> str:
        """Get the power state of the VM."""
        proc = _subprocess_run(
            [
                "az",
                "vm",
                "get-instance-view",
                "--subscription",
                self.azure_subscription,
                "--resource-group",
                self.temp_resource_group,
                "--name",
                self.vm_name,
                "--query",
                "instanceView.statuses[?starts_with(code,'PowerState/')].displayStatus",
                "-o",
                "tsv",
            ],
            artifacts_path=self.artifacts_path,
            artifact_name="az_vm_get_power_state",
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"failed to get VM power state {self.vm_name}: {proc.stderr}"
            )

        return proc.stdout.strip()

    def _is_vm_running(self) -> bool:
        """Check if the VM is running."""
        power_state = self._get_vm_powerstate()
        logger.debug("VM %s power state: %s", self.vm_name, power_state)
        return power_state == "VM running"

    def _start_vm(self) -> None:
        """Start the VM with retries if needed."""
        retries_remaining = 5
        while True:
            proc = _subprocess_run(
                [
                    "az",
                    "vm",
                    "start",
                    "--subscription",
                    self.azure_subscription,
                    "--resource-group",
                    self.temp_resource_group,
                    "--name",
                    self.vm_name,
                ],
                artifacts_path=self.artifacts_path,
                artifact_name="az_vm_start",
            )
            if proc.returncode == 0:
                return

            # Sometimes the VM start fails with a Conflict error due to
            # previous deallocate even though it technically finished.
            # Retry if this happens.
            if "Conflict" in proc.stderr and retries_remaining > 0:
                logger.warning(
                    "start VM %s failed with Conflict, retrying... (%d attempts left)",
                    self.vm_name,
                    retries_remaining,
                )
                time.sleep(5)
                retries_remaining -= 1
                continue

            raise RuntimeError(f"failed to start VM {self.vm_name}: {proc.stderr}")

    def _reboot_vm(self) -> None:
        """Reboot the VM."""
        self._execute_ssh_command(["reboot"], artifact_name="reboot")
        time.sleep(10)
        self._wait_for_vm()

    def _verify_image(self) -> None:
        """Verify the image has scrubbed conflicting configurations."""
        for config in [
            "/etc/NetworkManager/conf.d/99-azure-unmanaged-devices.conf",
            "/etc/udev/rules.d/68-azure-sriov-nm-unmanaged.rules",
        ]:
            proc = self._execute_ssh_command(
                ["test", "-f", config],
                artifact_name=f"verify-image-{os.path.basename(config)}",
            )
            if proc.returncode == 0:
                msg = f"config {config} found in {self.image}"
                logger.error(msg)

    def _wait_for_vm(self) -> None:
        """Wait for the VM to be ready."""
        deadline = datetime.now(timezone.utc) + timedelta(minutes=30)
        while datetime.now(timezone.utc) < deadline:
            logger.debug("waiting for VM to be ready on boot %s...", self.boot_id)
            if not self._is_vm_running():
                logger.debug("VM %s is not running, starting...", self.vm_name)
                self._start_vm()

            # Refresh boot diagnostics on every loop in case something went wrong.
            self._fetch_boot_diagnostics()

            proc = self._execute_ssh_command(
                ["systemctl", "is-system-running", "--wait"],
                artifact_name="systemctl-status",
            )
            status = proc.stdout.strip()
            if not status:
                status = "failed to ssh"

            logger.debug("VM status: %s", status)
            if status in ("running", "degraded"):
                # Ensure cloud-init is done before proceeding too.
                self._execute_ssh_command(
                    ["cloud-init", "status", "--wait"],
                    artifact_name="cloud-init-status",
                )
                return

            logger.debug("debug: %s bash", shlex.join(self.ssh_command))
            logger.debug(
                "       az serial-console connect --name %s --resource-group %s",
                self.vm_name,
                self.temp_resource_group,
            )
            time.sleep(2)

        raise RuntimeError(
            f"VM {self.vm_name} did not become ready in time after 30 minutes: {self.artifacts_path.as_posix()}"
        )

    def run_test(self) -> None:
        """Create VM and run self-tests."""
        try:
            logger.debug("artifacts path: %s", self.artifacts_path.as_posix())
            logger.debug("public IP: %s", self.public_ip)
            self._create_vm()
            self._wait_for_vm()
            self._scp_to_vm(
                self.selftest_script_path,
                self.target_script_path,
            )
            self._verify_image()

            for self.alloc in range(0, self.reallocates + 1):
                for self.boot in range(0, self.reboots + 1):
                    self._wait_for_vm()
                    self._fetch_boot_diagnostics()
                    self._fetch_logs()
                    self._run_selftest_script()
                    if self.boot < self.reboots:
                        self._reboot_vm()
                if self.alloc < self.reallocates:
                    self._deallocate_vm()
                    self._start_vm()
        except Exception as error:
            self.request.session.failed = True
            logger.error(
                "test failed: %r\nartifacts: %s\ntraceback: %s",
                error,
                self.artifacts_path.as_posix(),
                traceback.format_exc(),
            )
            raise RuntimeError(
                f"test failed: {error} @ {self.artifacts_path.as_posix()}"
            ) from error

    @pytest.mark.parametrize(
        "image",
        ARM64_IMAGES,
    )
    @pytest.mark.parametrize(
        "vm_size",
        ARM64_VM_SIZES,
    )
    def test_arm64(self, image, vm_size):
        """Test arm64 images."""
        self.run_test()

    @pytest.mark.parametrize(
        "image",
        GEN1_IMAGES,
    )
    @pytest.mark.parametrize(
        "vm_size",
        GEN1_VM_SIZES,
    )
    def test_gen1_x64(self, image, vm_size):
        """Test gen1 x64 images."""
        self.run_test()

    @pytest.mark.parametrize(
        "image",
        GEN2_IMAGES,
    )
    @pytest.mark.parametrize(
        "vm_size",
        GEN2_VM_SIZES,
    )
    def test_gen2_x64(self, image, vm_size):
        """Test gen2 x64 images."""
        self.run_test()
