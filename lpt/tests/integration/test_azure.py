#!/usr/bin/env python3

import base64
import json
import logging
import os
import time
import warnings
import zlib
from pathlib import Path

import pytest

from lpt.analyze import analyze_events
from lpt.cloudinit import CloudInit
from lpt.graph import ServiceGraph
from lpt.imds import InstanceMetadata
from lpt.journal import Journal
from lpt.ssh import SSH, SystemReadyTimeout
from lpt.systemd import Systemd

logger = logging.getLogger(__name__)

if os.environ.get("LPT_TEST_AZURE_IMAGES") != "1":
    pytest.skip("requires LPT_TEST_AZURE_IMAGES=1", allow_module_level=True)
elif not os.environ.get("LPT_TEST_AZURE_SUBSCRIPTION_ID"):
    pytest.skip("requires LPT_TEST_AZURE_SUBSCRIPTION_ID=<id>", allow_module_level=True)


def warn(warning: str) -> None:
    warnings.warn(UserWarning(warning))


@pytest.mark.parametrize(
    "vm_size", ["Standard_D2d_v5", "Standard_D2ds_v5", "Standard_DS1_v2"]
)
@pytest.mark.parametrize(
    "image",
    [
        "almalinux:almalinux:8_5-gen2:latest",
        "almalinux:almalinux:8_5:latest",
        "canonical:0001-com-ubuntu-minimal-bionic:minimal-18_04-lts-gen2:latest",
        "canonical:0001-com-ubuntu-minimal-bionic:minimal-18_04-lts:latest",
        "canonical:0001-com-ubuntu-minimal-focal:minimal-20_04-lts-gen2:latest",
        "canonical:0001-com-ubuntu-minimal-focal:minimal-20_04-lts:latest",
        "canonical:0001-com-ubuntu-minimal-jammy:minimal-22_04-lts-gen2:latest",
        "canonical:0001-com-ubuntu-minimal-jammy:minimal-22_04-lts:latest",
        "canonical:0001-com-ubuntu-server-focal:20_04-lts-gen2:latest",
        "canonical:0001-com-ubuntu-server-focal:20_04-lts:latest",
        "canonical:0001-com-ubuntu-server-jammy:22_04-lts-gen2:latest",
        "canonical:0001-com-ubuntu-server-jammy:22_04-lts:latest",
        "canonical:ubuntuserver:18.04-lts:latest",
        "canonical:ubuntuserver:18_04-lts-gen2:latest",
        "debian:debian-10:10-gen2:latest",
        "debian:debian-10:10:latest",
        "debian:debian-11:11-gen2:latest",
        "debian:debian-11:11:latest",
        "kinvolk:flatcar-container-linux-free:stable-gen2:latest",
        "kinvolk:flatcar-container-linux-free:stable:latest",
        "microsoftcblmariner:cbl-mariner:1-gen2:latest",
        "microsoftcblmariner:cbl-mariner:cbl-mariner-1:latest",
        "microsoftcblmariner:cbl-mariner:cbl-mariner-2-gen2:latest",
        "microsoftcblmariner:cbl-mariner:cbl-mariner-2:latest",
        "openlogic:centos:7_9-gen2:latest",
        "openlogic:centos:7_9:latest",
        "oracle:oracle-linux:ol79-gen2:latest",
        "oracle:oracle-linux:ol79:latest",
        "oracle:oracle-linux:ol84-lvm-gen2:latest",
        "oracle:oracle-linux:ol84-lvm:latest",
        "redhat:rhel:7-lvm:latest",
        "redhat:rhel:79-gen2:latest",
        "redhat:rhel:7_9:latest",
        "redhat:rhel:7lvm-gen2:latest",
        "redhat:rhel:8-lvm-gen2:latest",
        "redhat:rhel:8-lvm:latest",
        "redhat:rhel:8.1:latest",
        "redhat:rhel:8.2:latest",
        "redhat:rhel:81gen2:latest",
        "redhat:rhel:82gen2:latest",
        "redhat:rhel:84-gen2:latest",
        "redhat:rhel:85-gen2:latest",
        "redhat:rhel:86-gen2:latest",
        "redhat:rhel:8_4:latest",
        "redhat:rhel:8_5:latest",
        "redhat:rhel:8_6:latest",
        "redhat:rhel:9-lvm-gen2:latest",
        "redhat:rhel:9-lvm:latest",
        "redhat:rhel:90-gen2:latest",
        "redhat:rhel:9_0:latest",
        "suse:sles-12-sp5:gen1:latest",
        "suse:sles-12-sp5:gen2:latest",
        "suse:sles-15-sp2:gen2:latest",
        "suse:sles-15-sp3:gen1:latest",
        "suse:sles-15-sp3:gen2:latest",
        "suse:sles-15-sp4:gen2:latest",
    ],
)
def test_azure_amd64_instances(
    admin_username,
    admin_password,
    azure,
    image,
    restrict_ssh_source_ip,
    rg,
    ssh,
    vm_name,
    vm_size,
):
    _launch_and_verify_instance(
        azure=azure,
        admin_username=admin_username,
        admin_password=admin_password,
        image=image,
        restrict_ssh_source_ip=restrict_ssh_source_ip,
        rg=rg,
        ssh=ssh,
        vm_name=vm_name,
        vm_size=vm_size,
    )


@pytest.mark.parametrize("vm_size", ["Standard_D4plds_v5"])
@pytest.mark.parametrize(
    "image",
    [
        "canonical:0001-com-ubuntu-server-focal:20_04-lts-arm64:latest",
        "canonical:0001-com-ubuntu-server-jammy:22_04-lts-arm64:latest",
        "canonical:ubuntuserver:18_04-lts-arm64:latest",
        "debian:debian-11-arm64:11-backports:latest",
        "microsoftcblmariner:cbl-mariner:cbl-mariner-2-arm64:latest",
        "openlogic:centos:7_9-arm64:latest",
        "redhat:rhel-arm64:8_6-arm64:latest",
        "suse:sles-15-sp4-arm64:gen2:latest",
    ],
)
def test_azure_arm64_instances(
    admin_username,
    admin_password,
    azure,
    image,
    restrict_ssh_source_ip,
    rg,
    ssh,
    vm_name,
    vm_size,
):
    _launch_and_verify_instance(
        admin_username=admin_username,
        admin_password=admin_password,
        azure=azure,
        image=image,
        restrict_ssh_source_ip=restrict_ssh_source_ip,
        rg=rg,
        ssh=ssh,
        vm_name=vm_name,
        vm_size=vm_size,
    )


def _launch_and_verify_instance(
    admin_username,
    admin_password,
    azure,
    image,
    restrict_ssh_source_ip,
    rg,
    ssh,
    vm_name,
    vm_size,
):
    vm, public_ips = azure.launch_vm(
        admin_username=admin_username,
        admin_password=admin_password,
        image=image,
        name=vm_name,
        num_nics=1,
        rg=rg,
        vm_size=vm_size,
        ssh_pubkey_path=ssh.public_key,
        disk_size_gb=64,
        restrict_ssh_ip=restrict_ssh_source_ip,
        storage_sku=None,
    )

    host = public_ips[0].ip_address
    ssh.host = host
    ssh.user = admin_username
    for boot_num in range(0, 2):
        output_dir = Path(
            "/tmp",
            "lpt-tests",
            image.replace(":", "_"),
            vm_size,
            vm_name,
            f"boot_{boot_num}",
        )
        output_dir.mkdir(exist_ok=True, parents=True)

        if boot_num > 0:
            ssh.reboot()
            ssh.close()
            time.sleep(120)

        ssh.connect_with_retries()
        logger.info("Connected: %s@%s", admin_username, public_ips[0].ip_address)

        _verify_boot(image=image, output_dir=output_dir, ssh=ssh)

    ssh.close()


def _verify_boot(*, image: str, output_dir: Path, ssh: SSH):
    try:
        system_status = ssh.wait_for_system_ready()
    except SystemReadyTimeout as error:
        system_status = error.status
        warn(f"Systemd timed out for image={image} (status={system_status})")

    ssh.run(["sudo", "sync"], capture_output=False, check=False)

    journals = Journal.load_remote(ssh, output_dir=output_dir)
    assert len(journals) > 0

    systemd = Systemd.load_remote(ssh, output_dir=output_dir)
    assert systemd

    cloudinits = CloudInit.load_remote(ssh, output_dir=output_dir)
    if image.startswith("kinvolk"):
        assert len(cloudinits) == 0
    else:
        assert len(cloudinits) > 0

    instance_metadata = InstanceMetadata.load_remote(ssh, output_dir=output_dir)
    assert instance_metadata.metadata["compute"]["name"]

    event_data = analyze_events(
        journals=journals,
        cloudinits=cloudinits,
        systemd=systemd,
        boot=True,
        event_types=None,
    )

    out = output_dir / "events.json"
    out.write_text(json.dumps(event_data.events))
    out = output_dir / "events.json.zip.b64"
    out.write_text(b64_zip_json(event_data.events))

    out = output_dir / "warnings.json"
    out.write_text(json.dumps(event_data.warnings))
    out = output_dir / "warnings.json.zip.b64"
    out.write_text(b64_zip_json(event_data.warnings))

    # Raise warnings to tester.
    for warning in event_data.warnings:
        warn(f"warning for image={image}: {warning!r}")

    # Verify sample of cloud-init events.
    if not image.startswith("kinvolk"):
        for module in ["config-disk_setup", "config-growpart"]:
            events = [
                e
                for e in event_data.events
                if e["label"] == "CLOUDINIT_FRAME"
                and e["source"] == "cloudinit"
                and e["module"] == module
            ]
            assert (
                len(events) > 0
            ), f"missing cloudinit events for image={image} (module={module})"

    # Verify sample of journal events.
    for label in ["KERNEL_BOOT", "SYSTEMD_STARTED", "SSH_ACCEPTED_CONNECTION"]:
        events = [
            e
            for e in event_data.events
            if e["label"] == label and e["source"] == "journal"
        ]

        # Warn if kernel boot is missing, otherwise assert events are present.
        if len(events) == 0 and label == "KERNEL_BOOT":
            warn(f"missing events with for image={image} (label={label})")
        else:
            assert (
                len(events) > 0
            ), f"missing events with for image={image} (label={label})"

    # Verify sample of systemd events.
    for unit in ["local-fs.target", "basic.target"]:
        events = [
            e
            for e in event_data.events
            if e["label"] == "SYSTEMD_UNIT"
            and e["source"] == "systemd"
            and e["unit"] == unit
        ]

        assert (
            len(events) > 0
        ), f"missing systemd unit events with for image={image} (unit={unit})"

    # Verify sample of systemd events.
    events = [
        e
        for e in event_data.events
        if e["label"] == "SYSTEMD_SYSTEM" and e["source"] == "systemd"
    ]
    assert len(events) > 0, f"missing systemd system events for image={image})"

    # Verify system status is good.
    if system_status != "running":
        warn(f"system degraded for image={image} (status={system_status})")

    if cloudinits:
        frames = cloudinits[-1].get_frames()
    else:
        frames = []

    # Graph a sample of services/targets.
    for name in [
        "cloud-final.target",
        "ssh.service",
        "sshd.service",
        "network.target",
        "multi-user.target",
    ]:
        service = systemd.units.get(name)
        if not service or not service.is_active():
            continue

        digraph = ServiceGraph(
            name,
            filter_services=["systemd-journald.socket"],
            filter_conditional_result_no=True,
            systemd=systemd,
            frames=frames,
        ).generate_digraph()

        out = output_dir / f"graph-{name}.dot"
        out.write_text(digraph)
        out = output_dir / f"graph-{name}.dot.zip.b64"
        out.write_text(b64_zip(digraph))


def b64_zip(text: str) -> str:
    return base64.b64encode(zlib.compress(text.encode("utf-8"), level=9)).decode(
        "ascii"
    )


def b64_zip_json(obj):
    return b64_zip(json.dumps(obj))
