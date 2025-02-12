#!/usr/bin/env python3

# --------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.
# --------------------------------------------------------------------------

"""Azure VM utilities self-tests script."""

import argparse
import glob
import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional

import requests

logger = logging.getLogger("selftest")


# pylint: disable=line-too-long
# pylint: disable=too-many-instance-attributes
# pylint: disable=too-many-lines
# pylint: disable=too-many-locals


@dataclass(eq=True, repr=True)
class SkuConfig:
    """VM sku-specific configuration related to disks."""

    vm_size: str
    vm_size_type: Literal["arm64", "x64"] = "x64"
    nvme_controller_toggle_supported: bool = (
        False  # whether the sku supports NVMe controller toggle (Eb[d]s_v5)
    )
    nvme_only: bool = False  # NVMe-only skus (v6+)
    nvme_id_enabled_local: bool = False  # whether the sku supports NVMe ID locally
    nvme_id_enabled_remote: bool = False  # whether the sku supports NVMe ID remotely
    nvme_local_disk_count: int = 0
    nvme_local_disk_size_gib: int = 0
    temp_disk_size_gib: int = 0  # SCSI temp/resource disk size in GiB


@dataclass(eq=True, repr=True)
class V6SkuConfig(SkuConfig):
    """V6 VM sku-specific configuration related to disks."""

    nvme_only: bool = True
    nvme_id_enabled_local: bool = True
    nvme_id_enabled_remote: bool = False


def gb_to_gib(size_gb: int) -> int:
    """Roughly convert GB to GiB as sizes are documented in both ways."""
    return int(size_gb * (1000**3) / (1024**3))


SKU_CONFIGS = {
    "Standard_B2ts_v2": SkuConfig(vm_size="Standard_B2ts_v2"),
    # "Standard_D2s_v3": SkuConfig(vm_size="Standard_D2s_v3", temp_disk_size_gib=16),
    "Standard_D2s_v4": SkuConfig(vm_size="Standard_D2s_v4"),
    "Standard_D2ds_v4": SkuConfig(vm_size="Standard_D2ds_v4", temp_disk_size_gib=75),
    "Standard_D2s_v5": SkuConfig(vm_size="Standard_D2s_v5"),
    "Standard_D2ds_v5": SkuConfig(vm_size="Standard_D2ds_v5", temp_disk_size_gib=75),
    "Standard_D2ads_v5": SkuConfig(vm_size="Standard_D2ads_v5", temp_disk_size_gib=75),
    "Standard_D16ads_v5": SkuConfig(
        vm_size="Standard_D16ads_v5", temp_disk_size_gib=600
    ),
    "Standard_L8s_v2": SkuConfig(
        vm_size="Standard_L8s_v2",
        temp_disk_size_gib=80,
        nvme_local_disk_count=1,
        nvme_local_disk_size_gib=gb_to_gib(1920),
    ),
    "Standard_L8s_v3": SkuConfig(
        vm_size="Standard_L8s_v3",
        temp_disk_size_gib=80,
        nvme_local_disk_count=1,
        nvme_local_disk_size_gib=gb_to_gib(1920),
    ),
    "Standard_L80s_v3": SkuConfig(
        vm_size="Standard_L80s_v3",
        nvme_controller_toggle_supported=True,
        temp_disk_size_gib=800,
        nvme_local_disk_count=10,
        nvme_local_disk_size_gib=gb_to_gib(1920),
    ),
    "Standard_E2bs_v5": SkuConfig(
        vm_size="Standard_E2bs_v5", nvme_controller_toggle_supported=True
    ),
    "Standard_E2bds_v5": SkuConfig(
        vm_size="Standard_E2bds_v5",
        nvme_controller_toggle_supported=True,
        temp_disk_size_gib=75,
    ),
    "Standard_D2as_v6": V6SkuConfig(vm_size="Standard_D2als_v6"),
    "Standard_D2ads_v6": V6SkuConfig(
        vm_size="Standard_D2alds_v6",
        nvme_local_disk_count=1,
        nvme_local_disk_size_gib=110,
    ),
    "Standard_D16ads_v6": V6SkuConfig(
        vm_size="Standard_D16ads_v6",
        nvme_local_disk_count=2,
        nvme_local_disk_size_gib=440,
    ),
    "Standard_D32ads_v6": V6SkuConfig(
        vm_size="Standard_D32ads_v6",
        nvme_local_disk_count=4,
        nvme_local_disk_size_gib=440,
    ),
    "Standard_D2pls_v5": SkuConfig(
        vm_size="Standard_D2pls_v5",
        vm_size_type="arm64",
    ),
    "Standard_D2plds_v5": SkuConfig(
        vm_size="Standard_D2plds_v5",
        vm_size_type="arm64",
        temp_disk_size_gib=75,
    ),
    "Standard_D8pls_v5": SkuConfig(
        vm_size="Standard_D8pls_v5",
        vm_size_type="arm64",
    ),
    "Standard_D8plds_v5": SkuConfig(
        vm_size="Standard_D8plds_v5",
        vm_size_type="arm64",
        temp_disk_size_gib=300,
    ),
    "Standard_D2pls_v6": SkuConfig(
        vm_size="Standard_D2pls_v6",
        vm_size_type="arm64",
    ),
    "Standard_D2plds_v6": SkuConfig(
        vm_size="Standard_D2plds_v6",
        vm_size_type="arm64",
        nvme_local_disk_count=1,
        nvme_local_disk_size_gib=110,
    ),
    "Standard_D16pls_v6": SkuConfig(
        vm_size="Standard_D16pls_v6",
        vm_size_type="arm64",
    ),
    "Standard_D16plds_v6": SkuConfig(
        vm_size="Standard_D16plds_v6",
        vm_size_type="arm64",
        nvme_local_disk_count=2,
        nvme_local_disk_size_gib=440,
    ),
}


def device_sort(devices: List[str]) -> List[str]:
    """Natural sort for devices."""

    def natural_sort_key(s: str):
        # Natural sort by turning a string into a list of string and number chunks.
        # e.g. "nvme0n10" -> ["nvme", 0, "n", 10]
        return [
            int(text) if text.isdigit() else text for text in re.split("([0-9]+)", s)
        ]

    return sorted(devices, key=natural_sort_key)


def get_disk_size_gb(disk_path: str) -> int:
    """Get the size of the disk in GB."""
    try:
        proc = subprocess.run(
            ["lsblk", "-b", "-n", "-o", "SIZE", "-d", disk_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        logger.debug("lsblk output: %r", proc)
        size_bytes = int(proc.stdout.strip())
        size_gib = size_bytes // (1000**3)
        return size_gib
    except subprocess.CalledProcessError as error:
        logger.error("error while fetching disk size: %r", error)
        raise
    except FileNotFoundError:
        logger.error("lsblk command not found")
        raise


def get_disk_size_gib(disk_path: str) -> int:
    """Get the size of the disk in GiB."""
    try:
        proc = subprocess.run(
            ["lsblk", "-b", "-n", "-o", "SIZE", "-d", disk_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        logger.debug("lsblk output: %r", proc)
        size_bytes = int(proc.stdout.strip())
        size_gib = size_bytes // (1024**3)
        return size_gib
    except subprocess.CalledProcessError as error:
        logger.error("error while fetching disk size: %r", error)
        raise
    except FileNotFoundError:
        logger.error("lsblk command not found")
        raise


def get_imds_metadata() -> Dict:
    """Fetch IMDS metadata."""
    url = "http://169.254.169.254/metadata/instance?api-version=2021-02-01"
    headers = {"Metadata": "true"}

    try:
        response = requests.get(url, headers=headers, timeout=60)
        response.raise_for_status()
        metadata = response.json()
        logger.debug("fetched IMDS metadata: %r", metadata)
        return metadata
    except requests.RequestException as error:
        logger.error("error fetching IMDS metadata: %r", error)
        raise


def get_local_nvme_disks() -> List[str]:
    """Get all local NVMe disks."""
    local_disk_controllers = get_nvme_controllers_with_model(
        "Microsoft NVMe Direct Disk"
    )
    local_disk_controllers_v2 = get_nvme_controllers_with_model(
        "Microsoft NVMe Direct Disk v2"
    )

    return device_sort(
        [
            namespace
            for controller in local_disk_controllers + local_disk_controllers_v2
            for namespace in get_nvme_namespace_devices(controller)
        ]
    )


def get_remote_nvme_disks() -> List[str]:
    """Get all remote NVMe disks."""
    remote_disk_controllers = get_nvme_controllers_with_model(
        "MSFT NVMe Accelerator v1.0"
    )

    assert (
        len(remote_disk_controllers) <= 1
    ), f"unexpected number of remote controllers {remote_disk_controllers}"
    return device_sort(
        [
            namespace
            for controller in remote_disk_controllers
            for namespace in get_nvme_namespace_devices(controller)
        ]
    )


def get_nvme_controllers_with_model(model: str) -> List[str]:
    """Get a list of all NVMe controllers with the specified model."""
    nvme_controllers = []
    nvme_path = "/sys/class/nvme"

    for controller in glob.glob(os.path.join(nvme_path, "nvme*")):
        logger.debug("checking controller: %s", controller)
        model_path = os.path.join(controller, "model")
        try:
            with open(model_path, "r", encoding="utf-8") as file:
                controller_model = file.read().strip()
                logger.debug("controller: %s model: %s", controller, controller_model)
                if controller_model == model:
                    controller_name = controller.split("/")[-1]
                    nvme_controllers.append(controller_name)
        except FileNotFoundError:
            logger.debug("model file not found: %s", model_path)
            continue

    return device_sort(nvme_controllers)


def get_nvme_namespace_devices_with_model(model: str) -> List[str]:
    """Get all NVMe namespace devices for a given NVMe controller model."""
    controllers = get_nvme_controllers_with_model(model)
    logger.debug("controllers found for model=%s: %r", model, controllers)
    return device_sort(
        [
            namespace
            for controller in controllers
            for namespace in get_nvme_namespace_devices(controller)
        ]
    )


def get_nvme_namespace_devices(controller: str) -> List[str]:
    """Get all NVMe namespace devices for a given NVMe controller."""
    namespace_devices = []
    controller_name = controller.split("/")[-1]
    nvme_path = f"/sys/class/nvme/{controller_name}"

    logger.debug("checking namespaces under %s", nvme_path)
    for namespace in glob.glob(os.path.join(nvme_path, "nvme*")):
        logger.debug("checking namespace device: %s", namespace)
        if os.path.isdir(namespace):
            device_name = namespace.split("/")[-1]
            namespace_devices.append(device_name)

    return device_sort(namespace_devices)


def get_root_block_device() -> str:
    """Get the root block device using findmnt."""
    try:
        proc = subprocess.run(
            ["findmnt", "-n", "-o", "SOURCE", "/"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        logger.debug("findmnt output: %r", proc)
        return proc.stdout.strip()
    except subprocess.CalledProcessError as error:
        logger.error("error while fetching root block device: %r", error)
        raise
    except FileNotFoundError:
        logger.error("findmnt command not found")
        raise


def get_scsi_resource_disk() -> Optional[str]:
    """Get the SCSI resource disk device."""
    paths = [
        # cloud-init udev rules
        "/dev/disk/cloud/azure_resource",
        # gen2
        "/dev/disk/by-path/acpi-VMBUS:00-vmbus-f8b3781a1e824818a1c363d806ec15bb-lun-1",
        # gen1
        "/dev/disk/by-path/acpi-VMBUS:01-vmbus-000000000001*-lun-0",
    ]

    for path in paths:
        if "*" in path:
            matched_paths = glob.glob(path)
            for matched_path in matched_paths:
                resolved_path = os.path.realpath(matched_path)
                if os.path.exists(resolved_path):
                    return resolved_path.split("/")[-1]
        else:
            if os.path.exists(path):
                resolved_path = os.path.realpath(path)
                if os.path.exists(resolved_path):
                    return resolved_path.split("/")[-1]

    logger.info("no SCSI resource disk found")
    return None


DEV_DISK_AZURE_RESOURCE = "/dev/disk/azure/resource"


@dataclass(eq=True, repr=True)
class DiskInfo:
    """Information about different types of disks present."""

    root_device: str
    dev_disk_azure_links: List[str] = field(default_factory=list)
    dev_disk_azure_resource_disk: Optional[str] = None  # resolved path
    dev_disk_azure_resource_disk_size_gib: int = 0
    nvme_local_disk_size_gib: int = 0
    nvme_local_disks_v1: List[str] = field(default_factory=list)
    nvme_local_disks_v2: List[str] = field(default_factory=list)
    nvme_local_disks: List[str] = field(default_factory=list)
    nvme_remote_data_disks: List[str] = field(default_factory=list)
    nvme_remote_disks: List[str] = field(default_factory=list)
    nvme_remote_os_disk: Optional[str] = None
    root_device_is_nvme: bool = False
    scsi_resource_disk: Optional[str] = None
    scsi_resource_disk_size_gib: int = 0

    @classmethod
    def gather(cls) -> "DiskInfo":
        """Gather disk information and return an instance of DiskInfo."""
        dev_disk_azure_links = device_sort(
            [
                link
                for link in glob.glob(
                    os.path.join("/dev/disk/azure", "**"), recursive=True
                )
                if os.path.islink(link)
            ]
        )

        dev_disk_azure_resource_disk = None
        dev_disk_azure_resource_disk_size_gib = 0
        if os.path.exists(DEV_DISK_AZURE_RESOURCE):
            dev_disk_azure_resource_disk = os.path.realpath(DEV_DISK_AZURE_RESOURCE)
            dev_disk_azure_resource_disk_size_gib = get_disk_size_gib(
                dev_disk_azure_resource_disk
            )

        nvme_local_disks_v1 = get_nvme_namespace_devices_with_model(
            "Microsoft NVMe Direct Disk"
        )
        nvme_local_disks_v2 = get_nvme_namespace_devices_with_model(
            "Microsoft NVMe Direct Disk v2"
        )
        nvme_local_disks = device_sort(nvme_local_disks_v1 + nvme_local_disks_v2)
        nvme_local_disk_size_gib = 0
        if nvme_local_disks:
            nvme_local_disk_size_gib = min(
                get_disk_size_gib(f"/dev/{disk}") for disk in nvme_local_disks
            )
            local_disk_max_size = max(
                get_disk_size_gib(f"/dev/{disk}") for disk in nvme_local_disks
            )
            assert (
                nvme_local_disk_size_gib == local_disk_max_size
            ), f"local disk size mismatch: {nvme_local_disk_size_gib} != {local_disk_max_size} for {nvme_local_disks}"

        nvme_remote_disks = get_remote_nvme_disks()
        if nvme_remote_disks:
            nvme_remote_os_disk = nvme_remote_disks.pop(0)
            nvme_remote_data_disks = nvme_remote_disks
        else:
            nvme_remote_os_disk = None
            nvme_remote_data_disks = []

        root_device = get_root_block_device()
        root_device_is_nvme = root_device.startswith("/dev/nvme")
        root_device = root_device.split("/")[-1]

        scsi_resource_disk = get_scsi_resource_disk()
        scsi_resource_disk_size_gib = (
            get_disk_size_gib(f"/dev/{scsi_resource_disk}") if scsi_resource_disk else 0
        )

        disk_info = cls(
            dev_disk_azure_links=dev_disk_azure_links,
            dev_disk_azure_resource_disk=dev_disk_azure_resource_disk,
            dev_disk_azure_resource_disk_size_gib=dev_disk_azure_resource_disk_size_gib,
            nvme_local_disk_size_gib=nvme_local_disk_size_gib,
            nvme_local_disks_v1=nvme_local_disks_v1,
            nvme_local_disks_v2=nvme_local_disks_v2,
            nvme_local_disks=nvme_local_disks,
            nvme_remote_os_disk=nvme_remote_os_disk,
            nvme_remote_data_disks=nvme_remote_data_disks,
            nvme_remote_disks=nvme_remote_disks,
            root_device=root_device,
            root_device_is_nvme=root_device_is_nvme,
            scsi_resource_disk=scsi_resource_disk,
            scsi_resource_disk_size_gib=scsi_resource_disk_size_gib,
        )

        logger.info("disks info: %r", disk_info)
        return disk_info


@dataclass
class AzureNvmeIdDevice:
    """Azure NVMe ID device."""

    device: str
    model: Optional[str]
    nvme_id: str
    type: Optional[str]
    index: Optional[int]
    lun: Optional[int]
    name: Optional[str]
    extra: Dict[str, str]


@dataclass(repr=True)
class AzureNvmeIdInfo:
    """Azure NVMe ID."""

    azure_nvme_id_stdout: str
    azure_nvme_id_stderr: str
    azure_nvme_id_returncode: int
    azure_nvme_id_disks: Dict[str, AzureNvmeIdDevice]

    azure_nvme_id_json_stdout: str
    azure_nvme_id_json_stderr: str
    azure_nvme_id_json_returncode: int
    azure_nvme_id_json_disks: Dict[str, AzureNvmeIdDevice]

    azure_nvme_id_help_stdout: str
    azure_nvme_id_help_stderr: str
    azure_nvme_id_help_returncode: int

    azure_nvme_id_version_stdout: str
    azure_nvme_id_version_stderr: str
    azure_nvme_id_version_returncode: int
    azure_nvme_id_version: str

    azure_nvme_id_zzz_stdout: str
    azure_nvme_id_zzz_stderr: str
    azure_nvme_id_zzz_returncode: int

    def _validate_azure_nvme_disks(
        self, azure_nvme_id_disks: Dict[str, AzureNvmeIdDevice], disk_info: DiskInfo
    ) -> None:
        disk_cfg: Optional[AzureNvmeIdDevice] = None
        for device_name, disk_cfg in azure_nvme_id_disks.items():
            assert f"/dev/{device_name}" == disk_cfg.device
            assert disk_cfg.device.startswith(
                "/dev/nvme"
            ), f"unexpected device: {disk_cfg}"

        for device_name in disk_info.nvme_local_disks_v2:
            assert (
                device_name in azure_nvme_id_disks
            ), f"missing azure-nvme-id for {device_name}"
            disk_cfg = azure_nvme_id_disks.get(device_name)
            assert disk_cfg, f"failed to find azure-nvme-id for {device_name}"
            assert disk_cfg.type == "local", f"unexpected local disk type {disk_cfg}"
            assert disk_cfg.name, f"unexpected local disk name {disk_cfg}"
            assert disk_cfg.index, f"unexpected local disk index {disk_cfg}"
            assert disk_cfg.lun is None, f"unexpected local disk lun {disk_cfg}"
            assert disk_cfg.nvme_id, f"unexpected local disk id {disk_cfg}"
            assert not disk_cfg.extra, f"unexpected local disk extra {disk_cfg}"

        for device_name in disk_info.nvme_local_disks_v1:
            assert (
                device_name in azure_nvme_id_disks
            ), f"missing azure-nvme-id for {device_name}"
            disk_cfg = azure_nvme_id_disks.get(device_name)
            assert disk_cfg, f"failed to find azure-nvme-id for {device_name}"
            assert disk_cfg.type == "local", f"unexpected disk type {disk_cfg}"
            assert not disk_cfg.name, f"unexpected disk name {disk_cfg}"
            assert not disk_cfg.index, f"unexpected disk index {disk_cfg}"
            assert disk_cfg.lun is None, f"unexpected local disk lun {disk_cfg}"
            assert disk_cfg.nvme_id, f"unexpected disk id {disk_cfg}"
            assert not disk_cfg.extra, f"unexpected disk extra {disk_cfg}"

        for device_name in disk_info.nvme_remote_disks:
            assert (
                device_name in azure_nvme_id_disks
            ), f"missing azure-nvme-id for {device_name}"
            disk_cfg = azure_nvme_id_disks.get(device_name)
            assert disk_cfg, f"failed to find azure-nvme-id for {device_name}"
            assert disk_cfg.type in (
                "os",
                "data",
            ), f"unexpected remote disk type {disk_cfg}"
            if disk_cfg.type == "data":
                assert (
                    disk_cfg.lun is not None and disk_cfg.lun >= 0
                ), f"unexpected remote disk index {disk_cfg}"
            else:
                assert disk_cfg.lun is None, f"unexpected remote disk index {disk_cfg}"
            assert not disk_cfg.name, f"unexpected remote disk name {disk_cfg}"
            assert disk_cfg.nvme_id, f"unexpected remote disk id {disk_cfg}"
            assert not disk_cfg.extra, f"unexpected remote disk extra {disk_cfg}"

    def validate_azure_nvme_id(self, disk_info: DiskInfo) -> None:
        """Validate azure-nvme-id outputs."""
        assert self.azure_nvme_id_returncode == 0, "azure-nvme-id failed"
        if not os.path.exists("/sys/class/nvme"):
            assert (
                self.azure_nvme_id_stderr
                == "no NVMe devices in /sys/class/nvme: No such file or directory\n"
            ), f"unexpected azure-nvme-id stderr without /sys/class/nvme: {self.azure_nvme_id_stderr}"
        else:
            assert (
                self.azure_nvme_id_stderr == ""
            ), f"unexpected azure-nvme-id stderr: {self.azure_nvme_id_stderr}"

        self._validate_azure_nvme_disks(self.azure_nvme_id_disks, disk_info)
        logger.info("validate_azure_nvmve_id OK: %r", self.azure_nvme_id_stdout)

    def validate_azure_nvme_id_help(self) -> None:
        """Validate azure-nvme-id --help outputs."""
        assert self.azure_nvme_id_help_returncode == 0, "azure-nvme-id --help failed"
        assert (
            self.azure_nvme_id_help_stderr == ""
        ), f"unexpected azure-nvme-id --help stderr: {self.azure_nvme_id_help_stderr}"
        assert (
            self.azure_nvme_id_help_stdout
            and self.azure_nvme_id_help_stdout.startswith("Usage: azure-nvme-id ")
        ), "unexpected azure-nvme-id --help stdout: {self.azure_nvme_id_help_stdout}"

        logger.info("validate_azure_nvme_id_help OK: {self.azure_nvme_id_help_stdout}")

    def validate_azure_nvme_id_json(self, disk_info: DiskInfo) -> None:
        """Validate azure-nvme-id --format json outputs."""
        assert self.azure_nvme_id_json_returncode == 0, "azure-nvme-id failed"
        if not os.path.exists("/sys/class/nvme"):
            assert (
                self.azure_nvme_id_json_stderr
                == "no NVMe devices in /sys/class/nvme: No such file or directory\n"
            ), f"unexpected azure-nvme-id stderr without /sys/class/nvme: {self.azure_nvme_id_json_stderr}"
        else:
            assert (
                self.azure_nvme_id_json_stderr == ""
            ), f"unexpected azure-nvme-id stderr: {self.azure_nvme_id_json_stderr}"

        self._validate_azure_nvme_disks(self.azure_nvme_id_disks, disk_info)

        assert all(
            disk.model
            in (
                "MSFT NVMe Accelerator v1.0",
                "Microsoft NVMe Direct Disk",
                "Microsoft NVMe Direct Disk v2",
            )
            for disk in self.azure_nvme_id_json_disks.values()
        ), "missing model in azure-nvme-id --format json"
        logger.info(
            "validate_azure_nvmve_id_json OK: %r", self.azure_nvme_id_json_stdout
        )

    def validate_azure_nvme_id_version(self) -> None:
        """Validate azure-nvme-id --version outputs."""
        assert (
            self.azure_nvme_id_version_returncode == 0
        ), "azure-nvme-id --version failed"
        assert (
            self.azure_nvme_id_version_stderr == ""
        ), f"unexpected azure-nvme-id stderr: {self.azure_nvme_id_stderr}"
        assert self.azure_nvme_id_version_stdout, "missing azure-nvme-id version stdout"
        assert re.match(
            r"azure-nvme-id [0v]\.*", self.azure_nvme_id_version_stdout.strip()
        ), f"unexpected azure-nvme-id version stdout: {self.azure_nvme_id_version_stdout}"
        assert re.match(
            r"[0v]\.*", self.azure_nvme_id_version
        ), f"unexpected azure-nvme-id version: {self.azure_nvme_id_version}"

        logger.info("validate_azure_nvme_id_version OK: %s", self.azure_nvme_id_version)

    def validate_azure_nvme_id_zzz_invalid_arg(self) -> None:
        """Validate azure-nvme-id handles invalid arguments."""
        assert (
            self.azure_nvme_id_zzz_returncode == 1
        ), f"azure-nvme-id zzz rc={self.azure_nvme_id_zzz_returncode}"
        assert (
            self.azure_nvme_id_zzz_stderr == "invalid argument: zzz\n"
        ), f"unexpected azure-nvme-id zzz stderr: {self.azure_nvme_id_zzz_stderr}"
        assert (
            self.azure_nvme_id_zzz_stdout
            and self.azure_nvme_id_zzz_stdout.startswith("Usage: azure-nvme-id ")
        ), (f"unexpected azure-nvme-id zzz stdout: {self.azure_nvme_id_zzz_stdout}")

        logger.info(
            "validate_azure_nvme_id_invalid_arg OK: %r", self.azure_nvme_id_zzz_stdout
        )

    def validate(self, disk_info: DiskInfo) -> None:
        """Validate Azure NVMe ID output."""
        self.validate_azure_nvme_id_help()
        self.validate_azure_nvme_id_version()
        self.validate_azure_nvme_id_zzz_invalid_arg()
        self.validate_azure_nvme_id(disk_info)
        self.validate_azure_nvme_id_json(disk_info)

    @classmethod
    def gather(cls) -> "AzureNvmeIdInfo":
        """Gather Azure NVMe ID information."""
        proc = subprocess.run(["azure-nvme-id"], capture_output=True, check=False)
        azure_nvme_id_stdout = proc.stdout.decode("utf-8")
        azure_nvme_id_stderr = proc.stderr.decode("utf-8")
        azure_nvme_id_returncode = proc.returncode
        azure_nvme_id_disks = cls.parse_azure_nvme_id_output(azure_nvme_id_stdout)

        proc = subprocess.run(
            ["azure-nvme-id", "--format", "json"], capture_output=True, check=False
        )
        azure_nvme_id_json_stdout = proc.stdout.decode("utf-8")
        azure_nvme_id_json_stderr = proc.stderr.decode("utf-8")
        azure_nvme_id_json_returncode = proc.returncode
        azure_nvme_id_json_disks = cls.parse_azure_nvme_id_json_output(
            azure_nvme_id_json_stdout
        )

        proc = subprocess.run(
            ["azure-nvme-id", "--help"], capture_output=True, check=False
        )
        azure_nvme_id_help_stdout = proc.stdout.decode("utf-8")
        azure_nvme_id_help_stderr = proc.stderr.decode("utf-8")
        azure_nvme_id_help_returncode = proc.returncode

        proc = subprocess.run(
            ["azure-nvme-id", "--version"], capture_output=True, check=False
        )
        azure_nvme_id_version_stdout = proc.stdout.decode("utf-8")
        azure_nvme_id_version_stderr = proc.stderr.decode("utf-8")
        azure_nvme_id_version_returncode = proc.returncode
        azure_nvme_id_version = cls.parse_azure_nvme_id_version(
            azure_nvme_id_version_stdout
        )

        proc = subprocess.run(
            ["azure-nvme-id", "zzz"], capture_output=True, check=False
        )
        azure_nvme_id_zzz_stdout = proc.stdout.decode("utf-8")
        azure_nvme_id_zzz_stderr = proc.stderr.decode("utf-8")
        azure_nvme_id_zzz_returncode = proc.returncode

        azure_nvme_id_info = cls(
            azure_nvme_id_stdout=azure_nvme_id_stdout,
            azure_nvme_id_stderr=azure_nvme_id_stderr,
            azure_nvme_id_returncode=azure_nvme_id_returncode,
            azure_nvme_id_help_stdout=azure_nvme_id_help_stdout,
            azure_nvme_id_help_stderr=azure_nvme_id_help_stderr,
            azure_nvme_id_help_returncode=azure_nvme_id_help_returncode,
            azure_nvme_id_disks=azure_nvme_id_disks,
            azure_nvme_id_json_stdout=azure_nvme_id_json_stdout,
            azure_nvme_id_json_stderr=azure_nvme_id_json_stderr,
            azure_nvme_id_json_returncode=azure_nvme_id_json_returncode,
            azure_nvme_id_json_disks=azure_nvme_id_json_disks,
            azure_nvme_id_version_stdout=azure_nvme_id_version_stdout,
            azure_nvme_id_version_stderr=azure_nvme_id_version_stderr,
            azure_nvme_id_version_returncode=azure_nvme_id_version_returncode,
            azure_nvme_id_version=azure_nvme_id_version,
            azure_nvme_id_zzz_returncode=azure_nvme_id_zzz_returncode,
            azure_nvme_id_zzz_stdout=azure_nvme_id_zzz_stdout,
            azure_nvme_id_zzz_stderr=azure_nvme_id_zzz_stderr,
        )
        logger.info("azure-nvme-id info: %r", azure_nvme_id_info)
        return azure_nvme_id_info

    @staticmethod
    def parse_azure_nvme_id_json_output(output: str) -> Dict[str, AzureNvmeIdDevice]:
        """Parse azure-nvme-id --format json output.
        Example output:
        [
            {
                "path": "/dev/nvme0n33",
                "model": "MSFT NVMe Accelerator v1.0",
                "properties": {
                    "type": "data",
                    "lun": 31
                },
                "vs": ""
            },
            {
                "path": "/dev/nvme1n1",
                "model": "Microsoft NVMe Direct Disk v2",
                "properties": {
                    "type": "local",
                    "index": 1,
                    "name": "nvme-440G-1"
                },
                "vs": "type=local,index=1,name=nvme-440G-1"
            }
        ]
        """
        devices = {}

        for device in json.loads(output):
            device_path = device["path"]
            model = device["model"]
            properties = device["properties"]
            device_type = properties.pop("type", None)
            device_index = (
                int(properties.pop("index")) if "index" in properties else None
            )
            device_lun = int(properties.pop("lun")) if "lun" in properties else None
            device_name = properties.pop("name", None)
            azure_nvme_id_device = AzureNvmeIdDevice(
                device=device_path,
                model=model,
                nvme_id=",".join([f"{k}={v}" for k, v in properties.items()]),
                type=device_type,
                index=device_index,
                lun=device_lun,
                name=device_name,
                extra=properties,
            )

            key = device_path.split("/")[-1]
            devices[key] = azure_nvme_id_device

        return devices

    @staticmethod
    def parse_azure_nvme_id_output(output: str) -> Dict[str, AzureNvmeIdDevice]:
        """Parse azure-nvme-id output.

        Example output:
        /dev/nvme0n1: type=os
        /dev/nvme0n2: type=data,lun=0
        /dev/nvme0n3: type=data,lun=1
        /dev/nvme1n1: type=local,index=1,name=nvme-440G-1
        /dev/nvme2n1: type=local,index=2,name=nvme-440G-2
        /dev/nvme3n1:
        """
        devices = {}

        for line in output.splitlines():
            parts = line.strip().split(":", 1)
            if parts[-1] == "":
                parts.pop()

            device = parts[0].strip()
            if len(parts) == 2:
                nvme_id = parts[1].strip()
                properties = dict(kv.split("=", 1) for kv in nvme_id.split(","))
            elif len(parts) == 1:
                nvme_id = ""
                properties = {}
            else:
                raise ValueError(f"unexpected azure-nvme-id output: {line}")

            device_type = properties.pop("type", None)
            device_index = (
                int(properties.pop("index")) if "index" in properties else None
            )
            device_lun = int(properties.pop("lun")) if "lun" in properties else None
            device_name = properties.pop("name", None)
            azure_nvme_id_device = AzureNvmeIdDevice(
                device=device,
                model=None,
                nvme_id=nvme_id,
                type=device_type,
                index=device_index,
                lun=device_lun,
                name=device_name,
                extra=properties,
            )

            key = device.split("/")[-1]
            devices[key] = azure_nvme_id_device

        return devices

    @staticmethod
    def parse_azure_nvme_id_version(azure_nvme_id_version_output: str) -> str:
        """Parse azure-nvme-id version output and return version info."""
        parts = azure_nvme_id_version_output.strip().split(" ")
        assert (
            len(parts) == 2
        ), f"unexpected azure-nvme-id version output: {azure_nvme_id_version_output}"
        return parts[1]


class AzureVmUtilsValidator:
    """Validate Azure VM utilities."""

    def __init__(self) -> None:
        self.azure_nvme_id_info = AzureNvmeIdInfo.gather()
        self.disk_info = DiskInfo.gather()
        self.imds_metadata = get_imds_metadata()
        self.vm_size = self.imds_metadata.get("compute", {}).get("vmSize")
        self.sku_config = SKU_CONFIGS.get(self.vm_size)

        logger.info("sku config: %r", self.sku_config)

    def validate_dev_disk_azure_links_data(self) -> None:
        """Validate /dev/disk/azure/data links.

        All data disks should have by-lun if azure-vm-utils is installed.
        Future variants of remote disks will include by-name.
        """
        imds_data_disks = (
            self.imds_metadata.get("compute", {})
            .get("storageProfile", {})
            .get("dataDisks", [])
        )
        expected_data_disks = len(imds_data_disks)
        data_disks = [
            link
            for link in self.disk_info.dev_disk_azure_links
            if link.startswith("/dev/disk/azure/data/by-lun")
        ]
        if self.disk_info.nvme_remote_disks:
            assert len(data_disks) == len(
                self.disk_info.nvme_remote_data_disks
            ), f"unexpected number of data disks: {data_disks} configured={self.disk_info.nvme_remote_data_disks}"

        assert (
            len(data_disks) == expected_data_disks
        ), f"unexpected number of data disks: {data_disks} IMDS configured={imds_data_disks} (note that IMDS may not be accurate)"

        # Verify disk sizes match up with IMDS configuration.
        for imds_disk in imds_data_disks:
            lun = imds_disk.get("lun")
            # Disk size is actually reported in GiB not GB.
            expected_size_gib = int(imds_disk.get("diskSizeGB"))
            disk_path = f"/dev/disk/azure/data/by-lun/{lun}"
            actual_size_gib = get_disk_size_gib(disk_path)
            assert (
                actual_size_gib == expected_size_gib
            ), f"disk size mismatch for {disk_path}: expected {expected_size_gib} GiB, found {actual_size_gib} GiB"

        logger.info("validate_dev_disk_azure_links_data OK: %r", data_disks)

    def validate_dev_disk_azure_links_local(self) -> None:
        """Validate /dev/disk/azure/local links.

        All local disks should have by-serial if azure-vm-utils is installed.
        If NVMe id is supported, by-index and by-name will be available as well.
        """
        local_disks = sorted(
            [
                link
                for link in self.disk_info.dev_disk_azure_links
                if link.startswith("/dev/disk/azure/local")
            ]
        )

        for key in ["index", "name", "serial"]:
            local_disks_by_key = sorted(
                [
                    link
                    for link in self.disk_info.dev_disk_azure_links
                    if link.startswith(f"/dev/disk/azure/local/by-{key}")
                ]
            )
            if key == "serial":
                expected_count = len(self.disk_info.nvme_local_disks)
            else:
                expected_count = len(self.disk_info.nvme_local_disks_v2)

            assert (
                len(local_disks_by_key) == expected_count
            ), f"unexpected number of local disks by-{key}: {local_disks_by_key} (expected {expected_count})"
            assert (
                not self.sku_config
                or not self.sku_config.nvme_id_enabled_local
                or len(local_disks_by_key) == self.sku_config.nvme_local_disk_count
            ), f"unexpected number of local disks by sku for by-{key}: {local_disks_by_key} (expected {expected_count})"

            if key == "name":
                for disk in local_disks_by_key:
                    name = disk.split("/")[-1]
                    assert name.startswith(
                        "nvme-"
                    ), f"unexpected local disk name: {name}"
                    match = re.match(r"nvme-(\d+)G-(\d+)", name)
                    assert (
                        match
                    ), f"local disk name does not conform to expected pattern: {name}"
                    size, index = match.groups()
                    assert (
                        size.isdigit() and index.isdigit()
                    ), f"invalid size or index in local disk name: {name}"

                    # Cross-check by-index links with by-name links.
                    by_index_path = f"/dev/disk/azure/local/by-index/{index}"
                    assert os.path.realpath(by_index_path) == os.path.realpath(
                        disk
                    ), f"mismatch between by-index and by-name links: {by_index_path} != {disk}"

        logger.info("validate_dev_disk_azure_links_local OK: %r", local_disks)

    def validate_dev_disk_azure_links_os(self) -> None:
        """Validate /dev/disk/azure/os link."""
        os_disk = "/dev/disk/azure/os"
        assert os_disk in self.disk_info.dev_disk_azure_links, f"missing {os_disk}"

        logger.info("validate_dev_disk_azure_links_os OK: %r", os_disk)

    def validate_dev_disk_azure_links_resource(self) -> None:
        """Validate /dev/disk/azure/resource link."""
        resource_disk = "/dev/disk/azure/resource"
        expected = (self.sku_config and self.sku_config.temp_disk_size_gib) or bool(
            self.disk_info.scsi_resource_disk
        )
        if expected:
            assert (
                resource_disk in self.disk_info.dev_disk_azure_links
            ), f"missing {resource_disk}"
        else:
            assert (
                resource_disk not in self.disk_info.dev_disk_azure_links
            ), f"unexpected {resource_disk}"

        logger.info("validate_dev_disk_azure_links_resource OK: %r", resource_disk)

    def validate_nvme_local_disks(self) -> None:
        """Validate NVMe local disks."""
        logger.info("validate_nvme_local_disks OK: %r", self.disk_info.nvme_local_disks)

    def validate_scsi_resource_disk(self) -> None:
        """Validate SCSI resource disk symlink and size."""
        assert (
            self.disk_info.scsi_resource_disk_size_gib
            == self.disk_info.dev_disk_azure_resource_disk_size_gib
        ), f"resource disk size mismatch: {self.disk_info}"
        if self.disk_info.scsi_resource_disk:
            assert (
                f"/dev/{self.disk_info.scsi_resource_disk}"
                == self.disk_info.dev_disk_azure_resource_disk
            ), f"unexpected resource disk path: {self.disk_info}"
        else:
            assert (
                self.disk_info.scsi_resource_disk is None
                and self.disk_info.dev_disk_azure_resource_disk is None
            ), f"unexpected resource disk path: {self.disk_info}"

        logger.info(
            "validate_scsi_resource_disk OK: /dev/disk/azure/resource => %s",
            self.disk_info.dev_disk_azure_resource_disk,
        )

    def validate_sku_config(self) -> None:
        """Validate SKU config."""
        if not self.sku_config:
            logger.warning(
                "validate_sku_config SKIPPED: no sku configuration for VM size %r",
                self.vm_size,
            )
            return

        assert (
            self.sku_config.vm_size == self.vm_size
        ), f"vm size mismatch: {self.sku_config.vm_size} != {self.vm_size}"
        assert (
            len(self.disk_info.nvme_local_disks)
            == self.sku_config.nvme_local_disk_count
        ), f"local disk count mismatch: {len(self.disk_info.nvme_local_disks)} != {self.sku_config.nvme_local_disk_count}"
        assert (
            self.disk_info.nvme_local_disk_size_gib
            == self.sku_config.nvme_local_disk_size_gib
        ), f"local disk size mismatch: {self.disk_info.nvme_local_disk_size_gib} != {self.sku_config.nvme_local_disk_size_gib}"
        assert (
            self.disk_info.scsi_resource_disk_size_gib
            == self.sku_config.temp_disk_size_gib
        ), f"temp disk size mismatch: {self.disk_info.scsi_resource_disk_size_gib} != {self.sku_config.temp_disk_size_gib}"
        assert (
            self.disk_info.dev_disk_azure_resource_disk_size_gib
            == self.sku_config.temp_disk_size_gib
        ), f"temp disk size mismatch: {self.disk_info.dev_disk_azure_resource_disk_size_gib} != {self.sku_config.temp_disk_size_gib}"

        logger.info("validate_sku_config OK: %r", self.sku_config)

    def validate(self) -> None:
        """Run validations."""
        self.azure_nvme_id_info.validate(self.disk_info)
        self.validate_dev_disk_azure_links_data()
        self.validate_dev_disk_azure_links_local()
        self.validate_dev_disk_azure_links_os()
        self.validate_dev_disk_azure_links_resource()
        self.validate_scsi_resource_disk()
        self.validate_sku_config()
        logger.info("success!")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Azure VM utilities self-tests script."
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(format="%(message)s", level=logging.DEBUG)
    else:
        logging.basicConfig(format="%(message)s", level=logging.INFO)

    validator = AzureVmUtilsValidator()
    validator.validate()


if __name__ == "__main__":
    main()
