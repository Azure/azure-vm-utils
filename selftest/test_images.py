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
        "debian:debian-13-daily:13-arm64:latest",
        "debian:debian-sid-daily:sid-arm64:latest",
        "/CommunityGalleries/Fedora-5e266ba4-2250-406d-adad-5d73860d958f/Images/Fedora-Cloud-Rawhide-Arm64/versions/latest",
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


def safe_parse_bytes_literal(s: str):
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
    deadline = datetime.now(timezone.utc) + timedelta(minutes=30)
    while datetime.now(timezone.utc) < deadline:
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

        if proc.returncode != 0 and proc.stderr.startswith("ssh:"):
            logger.debug("SSH failed, retrying...")
            time.sleep(5)
            continue

        if check and proc.returncode != 0:
            raise RuntimeError(
                f"Command '{printable_cmd}' failed with return code {proc.returncode}: {artifact_path.as_posix()}"
            )

        return proc

    raise RuntimeError(
        f"Command '{shlex.join(cmd)}' timed out after 30 minutes: {artifacts_path.as_posix()}"
    )


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
def reboots():
    """Get the number of reboots."""
    yield int(os.getenv("SELFTEST_REBOOTS", "50"))


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
        proc = _subprocess_run(
            [
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
            ],
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
    yield (datetime.now(timezone.utc) + timedelta(hours=8)).isoformat()


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
        self.boot = 0
        self.delete_after_tag = delete_after_tag
        self.hold_failures = hold_failures
        self.image = image
        self.nsg = os.getenv("SELFTEST_NSG")
        self.public_ip, self.public_ip_name = public_ip
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
        try:
            yield
        finally:
            if is_cleanup_permitted(request, hold_failures):
                logger.info("CLEANING:\n%s", self.vm_cfg)
                self._cleanup()
            else:
                logger.error(
                    "TEST FAILED, HOLDING RESOURCES FOR DEBUGGING:\n%s",
                    self.vm_cfg,
                )

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
        ]

        if self.admin_password:
            cmd += ["--admin-password", self.admin_password]

        if self.nsg:
            cmd += ["--nsg", self.nsg]

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

        logger.info("CREATED VM:\n%s", self.vm_cfg)
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
                artifact_name=f"boot{self.boot}-console",
                decode=True,
            )
            if proc.returncode == 0 and "BlobNotFound" not in proc.stderr:
                return

            time.sleep(1)

    def _fetch_logs(self) -> None:
        """Fetch logs."""
        proc = self._execute_ssh_command(
            ["journalctl", "-o", "short-monotonic", "-b"],
            artifact_name=f"boot{self.boot}-journal",
        )

        if proc.returncode != 0:
            raise RuntimeError(
                f"failed to fetch journalctl logs on boot {self.boot} @ {self.artifacts_path.as_posix()}: {proc.stderr}"
            )

        self._scp_from_vm("/var/log/cloud-init.log", f"boot{self.boot}-cloud-init.log")
        self._scp_from_vm(
            "/var/log/cloud-init-output.log", f"boot{self.boot}-cloud-init-output.log"
        )
        self._execute_ssh_command(
            ["rm", "-f", "/var/log/cloud-init.log", "/var/log/cloud-init-output.log"],
            artifact_name=f"boot{self.boot}-rm-logs",
        )

    def _run_selftest_script(self) -> None:
        """Run selftest script on the VM."""
        proc = self._execute_ssh_command(
            [self.target_script_path, "--debug"],
            artifact_name=f"boot{self.boot}-selftest",
        )

        if proc.returncode != 0:
            raise RuntimeError(
                f"self-test failed on boot {self.boot} @ {self.artifacts_path.as_posix()}: {proc.stderr}"
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
                raise RuntimeError(f"config {config} found in {self.image}")

    def _wait_for_vm(self) -> None:
        """Wait for the VM to be ready."""
        while True:
            logger.debug("waiting for VM to be ready on boot %d...", self.boot)
            self._execute_ssh_command(
                ["cloud-init", "status", "--wait"], artifact_name="cloud-init-status"
            )
            proc = self._execute_ssh_command(
                ["systemctl", "is-system-running", "--wait"],
                artifact_name="systemctl-status",
            )
            status = proc.stdout.strip()
            if not status:
                status = "failed to ssh"

            logger.debug("VM status: %s", status)
            if status in ("running", "degraded"):
                return

            logger.debug("debug: %s bash", shlex.join(self.ssh_command))
            logger.debug(
                "       az serial-console connect --name %s --resource-group %s",
                self.vm_name,
                self.temp_resource_group,
            )
            time.sleep(2)

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

            reboots = int(os.getenv("SELFTEST_REBOOTS", "50"))
            for self.boot in range(0, reboots):
                self._fetch_boot_diagnostics()
                self._fetch_logs()
                self._run_selftest_script()
                self._reboot_vm()
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
