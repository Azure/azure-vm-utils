#!/bin/bash

###########################################################################
# Test scenarios for azure-ephemeral-disk-setup service.
#
# This script is designed to test the behavior of the azure-ephemeral-disk-setup
# script under various conditions, simulating different disk configurations
# and ensuring that it behaves correctly in each case.
###########################################################################

set -euo pipefail
shopt -s nullglob

TMP_LOG="/tmp/azure-ephemeral-test.log"

# Ensure the script is run as root
if [[ $EUID -ne 0 ]]; then
    echo "This script must be run as root" >&2
    exit 1
fi

# Ensure disks are symlinked correctly if previous runs deleted them.
partprobe >/dev/null 2>&1

# Scan NVMe disks.
mapfile -t NVME_DISKS < <(
    for symlink in $(find /dev/disk/azure/local/by-serial/ -type l | sort); do
        # Skip entries that are partition symlinks (e.g., nvme0n1-part1) or not block devices.
        if [[ "$symlink" == *-part* || ! -b "$symlink" ]]; then
            continue
        fi
        echo "$symlink"
    done
)

# Ensure we have at least 2 local NVMe disks.
if [[ ${#NVME_DISKS[@]} -lt 2 ]]; then
    echo "Tests require at least 2 local NVMe disks. Found: ${#NVME_DISKS[@]}"
    exit 1
fi

echo "Detected ${#NVME_DISKS[@]} local NVMe disks"

# Ensure we have a SCSI resource disk.
RESOURCE_DISK="/dev/disk/azure/resource"
if [[ ! -b "$RESOURCE_DISK" ]]; then
    echo "Tests require SCSI resource disk at $RESOURCE_DISK"
    exit 1
fi

# Scrub /etc/fstab to remove any lines with 'comment=' then save a backup.
sed -i.bak "/comment=/d" /etc/fstab
FSTAB_SAVED_PATH="/etc/fstab.saved"
cp /etc/fstab "$FSTAB_SAVED_PATH"

# Allow for hiding mdadm/mkfs.xfs tools to test failure cases.
MDADM_PATH="$(command -v mdadm)"
MDADM_SAVED_PATH="$MDADM_PATH.saved"
MKFS_XFS_PATH="$(command -v mkfs.xfs)"
MKFS_XFS_SAVED_PATH="MKFS_XFS_PATH.saved"

# Create a temporary directory for fake binaries to mock tools.
FAKE_BIN_PATH="$(mktemp -d)"
PATH="$FAKE_BIN_PATH:$PATH"

configure_conf() {
    # Populates /etc/azure-ephemeral-disk-setup.conf with default settings, overriding
    # with KEY=VALUE arguments if provided.
    local key_value_pairs=("$@")
    local config_file="/etc/azure-ephemeral-disk-setup.conf"
    truncate -s 0 "$config_file"

    local pair
    for pair in "${key_value_pairs[@]}"; do
        echo "$pair" >>$config_file
    done
}

configure_nvme_disks() {
    # Configures NVMe local disks by creating symlinks in /dev/disk/azure/local/by-serial.
    # Takes optional # of disks to expose.  If unspecified, exposes all available local disks.
    local nvme_count=${#NVME_DISKS[@]}
    local desired_count="${1:-$nvme_count}"

    local i
    for i in $(seq 0 $(("${#NVME_DISKS[@]}" - 1))); do
        if [[ ! -b "${NVME_DISKS[$i]}" ]]; then
            echo "configure_nvme_disks: unexpected missing disk symlink ${NVME_DISKS[$i]}"
            exit 1
        fi

        if [[ $i -ge $desired_count ]]; then
            rm -f "${NVME_DISKS[$i]}"
        fi
    done
}

configure_scsi_resource_disk() {
    # Configures SCSI resource disk by managing /dev/disk/azure/resource symlink.
    # Takes argument of 0 (disabled) or 1 (enabled).
    local count="$1"

    if [[ $count -eq 0 ]]; then
        rm -f "$RESOURCE_DISK"
        return
    fi

    if [[ ! -b "$RESOURCE_DISK" ]]; then
        echo "configure_scsi_resource_disk: unexpectedly missing resource disk symlink"
        exit 1
    fi
}

disable_write_fstab() {
    chattr +i /etc/fstab
}

hide_mdadm() {
    mv "$MDADM_PATH" "$MDADM_SAVED_PATH"
}

hide_mkfs_xfs() {
    mv "$MKFS_XFS_PATH" "$MKFS_XFS_SAVED_PATH"
}

partprobe_safe() {
    # Sometimes a sync seems to be needed after partprobe. It may just be a
    # coincidence that the delay from sync is enough.
    # WARNING: partprobe will trigger symlinks to be re-created, make sure to
    # run configure_nvme_disks and configure_scsi_resource_disk AFTER running
    # this.
    partprobe >/dev/null 2>&1
    sync
}

reset_disk() {
    wipefs -q -a "$1" >/dev/null 2>&1 || true
}

reset_disks() {
    rm -f /dev/disk/azure/local/by-serial/fake*
    if findmnt /mnt >/dev/null 2>&1; then
        umount /mnt
    fi

    local disk
    for disk in /dev/md/*; do
        if findmnt "$disk" >/dev/null 2>&1; then
            umount "$disk"
        fi

        reset_disk "$disk"
        mdadm -q --stop "$disk"
    done

    for disk in "${NVME_DISKS[@]}" "$RESOURCE_DISK"; do
        [[ -b "$disk" ]] || continue
        if findmnt "$disk" >/dev/null 2>&1; then
            umount "$disk"
        fi
        reset_disk "$disk"
    done
    partprobe_safe

    configure_nvme_disks
    configure_scsi_resource_disk 1

    if [[ -b "$RESOURCE_DISK" ]]; then
        reset_ntfs_resource_disk
    fi
}

reset_fake_bin_dir() {
    rm -rf "${FAKE_BIN_PATH:?}"/*
}

reset_fstab() {
    chattr -i /etc/fstab
    if [[ -f "$FSTAB_SAVED_PATH" ]]; then
        cp "$FSTAB_SAVED_PATH" /etc/fstab
    fi
}

reset_mdadm() {
    if [[ -f "$MDADM_SAVED_PATH" ]]; then
        mv "$MDADM_SAVED_PATH" "$MDADM_PATH"
    fi
}

reset_mkfs_xfs() {
    if [[ -f "$MKFS_XFS_SAVED_PATH" ]]; then
        mv "$MKFS_XFS_SAVED_PATH" "$MKFS_XFS_PATH"
    fi
}

reset_ntfs_resource_disk() {
    parted -s "$RESOURCE_DISK" mklabel gpt mkpart primary ntfs 0% 100%
    partprobe_safe
    mkfs.ntfs -q --quick "${RESOURCE_DISK}-part1"
    mount "${RESOURCE_DISK}-part1" /mnt
    echo "This is a test NTFS file" >/mnt/dataloss_warning_readme.txt
    umount /mnt
}

reset() {
    reset_disks
    reset_fake_bin_dir
    reset_fstab
    reset_mdadm
    reset_mkfs_xfs
    configure_conf
    chmod 755 /mnt
}

on_exit() {
    echo "Cleaning up..."
    if findmnt /mnt >/dev/null 2>&1; then
        umount /mnt
    fi

    reset
    partprobe_safe
}
trap on_exit EXIT

assert_regex_in_log() {
    local expected_regex="$1"

    if ! grep -q "$expected_regex" "$TMP_LOG"; then
        echo "❌ $TEST_COUNT $TEST LOG ASSERTION FAILED: Expected \"$expected_regex\""
        exit 1
    fi
}

run_and_assert() {
    local expected_output="$1"
    local expected_code="$2"

    local actual_output
    local actual_code=0

    azure-ephemeral-disk-setup >$TMP_LOG.stdout 2>$TMP_LOG || actual_code=$?
    actual_output="$(cat $TMP_LOG.stdout)"
    echo "LOG FOR TEST: $TEST" >>$TMP_LOG

    if [[ "$actual_output" != "$expected_output" ]]; then
        echo "❌ $TEST_COUNT $TEST OUTPUT FAILED: Actual \"$actual_output\" != Expected \"$expected_output\""
        exit 1
    fi

    if [[ $actual_code -ne $expected_code ]]; then
        echo "❌ $TEST_COUNT $TEST EXIT CODE FAILED: Actual code=$actual_code != Expected code=$expected_code"
        exit 1
    fi

    echo "✅ $TEST_COUNT $TEST: $actual_output (code=$actual_code)"
}

test_format_failure_single_nvme() {
    configure_nvme_disks 1

    cp /bin/false "$FAKE_BIN_PATH/mkfs.xfs"
    hash -r

    run_and_assert "Formatting ${NVME_DISKS[0]} failed" 1
}

test_format_failure_aggregated_nvme() {
    configure_nvme_disks 2

    cp /bin/false "$FAKE_BIN_PATH/mkfs.xfs"
    hash -r

    run_and_assert "Formatting /dev/md/azure-ephemeral-md_0 failed" 1
}

test_format_failure_scsi_resource() {
    configure_nvme_disks 0
    configure_scsi_resource_disk 1
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"

    cp /bin/false "$FAKE_BIN_PATH/mkfs.xfs"
    hash -r

    run_and_assert "Formatting /dev/disk/azure/resource failed" 1
}

test_idempotent_rerun() {
    configure_nvme_disks 1

    run_and_assert "Mounted ${NVME_DISKS[0]} at /mnt with fs=xfs" 0
    run_and_assert "Already mounted and configured in /etc/fstab, nothing to do" 0
}

test_fstab_readonly() {
    configure_nvme_disks 1
    configure_conf
    disable_write_fstab

    run_and_assert "Mounted ${NVME_DISKS[0]} at /mnt with fs=xfs" 0
    assert_regex_in_log "WARNING: unable to persist mount to /etc/fstab"
}

test_fstab_readonly_reboot_single_nvme() {
    configure_nvme_disks 1
    configure_conf
    disable_write_fstab

    run_and_assert "Mounted ${NVME_DISKS[0]} at /mnt with fs=xfs" 0
    assert_regex_in_log "WARNING: unable to persist mount to /etc/fstab"

    # Simulate a reboot by resetting unmounting /mnt.
    umount /mnt

    run_and_assert "Mounted existing filesystem with label=AzureEphmDsk at /mnt" 0
}

test_fstab_readonly_reboot_already_mounted_elsewhere() {
    configure_nvme_disks 1
    configure_conf
    disable_write_fstab

    run_and_assert "Mounted ${NVME_DISKS[0]} at /mnt with fs=xfs" 0
    assert_regex_in_log "WARNING: unable to persist mount to /etc/fstab"

    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_MOUNT_POINT=/media"
    run_and_assert "Existing filesystem with label=AzureEphmDsk is already mounted at /mnt" 1
}

test_fstab_readonly_reboot_aggregated_nvme() {
    configure_nvme_disks 2
    configure_conf
    disable_write_fstab

    run_and_assert "Mounted /dev/md/azure-ephemeral-md_0 at /mnt with fs=xfs chunk=512K count=2" 0
    assert_regex_in_log "WARNING: unable to persist mount to /etc/fstab"

    # Simulate a reboot by resetting unmounting /mnt.
    umount /mnt

    run_and_assert "Mounted existing filesystem with label=AzureEphmDsk at /mnt" 0
}

test_fstab_readonly_idempotent_single_nvme() {
    configure_nvme_disks 1
    disable_write_fstab

    run_and_assert "Mounted ${NVME_DISKS[0]} at /mnt with fs=xfs" 0

    if ! grep -q "WARNING: unable to persist mount to /etc/fstab" "$TMP_LOG"; then
        echo "Expected warning about fstab not being writable was not found in log"
        exit 1
    fi

    run_and_assert "Mount point /mnt is already mounted, perhaps by another service" 1
}

test_fstab_readonly_idempotent_aggregated_nvme() {
    configure_nvme_disks 2
    disable_write_fstab

    run_and_assert "Mounted /dev/md/azure-ephemeral-md_0 at /mnt with fs=xfs chunk=512K count=2" 0

    if ! grep -q "WARNING: unable to persist mount to /etc/fstab" "$TMP_LOG"; then
        echo "Expected warning about fstab not being writable was not found in log"
        exit 1
    fi

    run_and_assert "Mount point /mnt is already mounted, perhaps by another service" 1
}

test_fstab_conflicting_entry() {
    echo "/dev/fake /mnt xfs defaults,comment=otherservice 0 2" >>/etc/fstab
    configure_nvme_disks 1

    run_and_assert "Aborting due to conflicting fstab entry for /mnt with source=/dev/fake target=/mnt fstype=xfs options=defaults,comment=otherservice" 1
}

test_broken_symlink_resource() {
    configure_nvme_disks 0
    configure_scsi_resource_disk 1
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"
    ln -sf /dev/nonexistent /dev/disk/azure/resource

    run_and_assert "Not a valid block device: /dev/disk/azure/resource" 1
}

test_broken_symlink_no_nvme() {
    configure_nvme_disks 0
    ln -sf /dev/nonexistent /dev/disk/azure/local/by-serial/fake

    run_and_assert "No local NVMe disks detected and AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=false, exiting without action" 0
    assert_regex_in_log "Ignoring /dev/disk/azure/local/by-serial/fake, not a block device"
}

test_broken_symlink_single_nvme() {
    configure_nvme_disks 1
    ln -sf /dev/nonexistent /dev/disk/azure/local/by-serial/fake

    run_and_assert "Mounted ${NVME_DISKS[0]} at /mnt with fs=xfs" 0
    assert_regex_in_log "Ignoring /dev/disk/azure/local/by-serial/fake, not a block device"
}

test_broken_symlink_multiple_nvme() {
    configure_nvme_disks 2
    ln -sf /dev/nonexistent /dev/disk/azure/local/by-serial/fake
    ln -sf /dev/nonexistent /dev/disk/azure/local/by-serial/fake2

    run_and_assert "Mounted /dev/md/azure-ephemeral-md_0 at /mnt with fs=xfs chunk=512K count=2" 0
    assert_regex_in_log "Ignoring /dev/disk/azure/local/by-serial/fake, not a block device"
    assert_regex_in_log "Ignoring /dev/disk/azure/local/by-serial/fake2, not a block device"
}

test_custom_mount() {
    configure_scsi_resource_disk 1
    configure_nvme_disks 0
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true" "AZURE_EPHEMERAL_DISK_SETUP_MOUNT_POINT=/mnt/custom"

    run_and_assert "Mounted /dev/disk/azure/resource at /mnt/custom with fs=xfs" 0
}

test_custom_mount_deep() {
    configure_scsi_resource_disk 1
    configure_nvme_disks 0
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true" "AZURE_EPHEMERAL_DISK_SETUP_MOUNT_POINT=/mnt/foo/bar/custom"

     run_and_assert "Mounted /dev/disk/azure/resource at /mnt/foo/bar/custom with fs=xfs" 0
}

test_custom_mdadm_chunk() {
    configure_scsi_resource_disk 0
    configure_nvme_disks 2
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_MDADM_CHUNK=1024K"

    run_and_assert "Mounted /dev/md/azure-ephemeral-md_0 at /mnt with fs=xfs chunk=1024K count=2" 0
}

test_custom_mdam_name() {
    configure_nvme_disks 2
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_MDADM_NAME=myraid"

    run_and_assert "Mounted /dev/md/myraid_0 at /mnt with fs=xfs chunk=512K count=2" 0
}

test_invalid_config_aggregation() {
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_AGGREGATION=invalid"
    run_and_assert "AZURE_EPHEMERAL_DISK_SETUP_AGGREGATION must be either 'mdadm' or 'none'." 1
}

test_invalid_config_fs_type() {
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_FS_TYPE=ntfs"
    run_and_assert "AZURE_EPHEMERAL_DISK_SETUP_FS_TYPE must be either 'ext4' or 'xfs'." 1
}

test_invalid_config_mdadm_chunk() {
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_MDADM_CHUNK=invalid"
    run_and_assert "AZURE_EPHEMERAL_DISK_SETUP_MDADM_CHUNK must be a positive integer followed by K, M, G, or T (e.g., 512K, 1M, 2G)." 1
}

test_invalid_config_mdadm_name() {
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_MDADM_NAME=invalid\ name"
    run_and_assert "AZURE_EPHEMERAL_DISK_SETUP_MDADM_NAME must be a valid name (alphanumeric, underscores, or hyphens)." 1
}

test_invalid_config_mount_point_path() {
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_MOUNT_POINT=relative/path"
    run_and_assert "AZURE_EPHEMERAL_DISK_SETUP_MOUNT_POINT must be an absolute path" 1
}

test_invalid_config_nvme_model_detection() {
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_NVME_MODEL_DETECTION=invalid"
    run_and_assert "AZURE_EPHEMERAL_DISK_SETUP_NVME_MODEL_DETECTION must be either 'true' or 'false'" 1
}

test_invalid_config_scsi_resource() {
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=invalid"
    run_and_assert "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE must be either 'true' or 'false'" 1
}

test_missing_mkfs_tool() {
    hide_mkfs_xfs

    run_and_assert "mkfs.xfs is not installed and is required for formatting" 1
}

test_missing_mdadm_tool() {
    hide_mdadm

    run_and_assert "mdadm is not installed and is required for disk aggregation" 1
}

test_mount_point_is_a_file() {
    configure_nvme_disks 1

    local temp_path
    temp_path="$(mktemp)"
    configure_conf AZURE_EPHEMERAL_DISK_SETUP_MOUNT_POINT="$temp_path"

    run_and_assert "Mount point $temp_path exists, but is not a directory" 1
    rm -f "$temp_path"
}

test_mount_point_is_a_symlink() {
    configure_nvme_disks 1

    local temp_path
    temp_path="$(mktemp)"

    local temp_path2
    temp_path2="$(mktemp)"

    ln -sf "$temp_path2" "$temp_path"
    configure_conf AZURE_EPHEMERAL_DISK_SETUP_MOUNT_POINT="$temp_path"

    run_and_assert "Mount point $temp_path exists, but is not a directory" 1

    rm -f "$temp_path"
    rm -f "$temp_path2"
}

test_no_nvme_or_managed_resource_disks() {
    configure_scsi_resource_disk 0
    configure_nvme_disks 0
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"

    run_and_assert "No local NVMe or SCSI resource disks detected, exiting without action" 0
}

test_no_nvme_or_unmanaged_resource_disks() {
    configure_scsi_resource_disk 0
    configure_nvme_disks 0

    run_and_assert "No local NVMe disks detected, exiting without action" 0
}

test_nvme_aggregation_disabled() {
    configure_nvme_disks 2
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_AGGREGATION=none"

    run_and_assert "Mounted ${NVME_DISKS[0]} at /mnt with fs=xfs" 0
    assert_regex_in_log "Multiple disks found but aggregation is disabled. Only using ${NVME_DISKS[0]}"
}

test_nvme_aggregation_max() {
    configure_scsi_resource_disk 0
    configure_nvme_disks ${#NVME_DISKS[@]}
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"

    run_and_assert "Mounted /dev/md/azure-ephemeral-md_0 at /mnt with fs=xfs chunk=512K count=${#NVME_DISKS[@]}" 0
}

test_nvme_aggregation_max_with_managed_resource() {
    configure_scsi_resource_disk 1
    configure_nvme_disks ${#NVME_DISKS[@]}
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"

    run_and_assert "Mounted /dev/md/azure-ephemeral-md_0 at /mnt with fs=xfs chunk=512K count=${#NVME_DISKS[@]}" 0
}

test_nvme_model_fallback_detection() {
    configure_scsi_resource_disk 0
    configure_nvme_disks 0
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_NVME_MODEL_DETECTION=true"

    run_and_assert "Mounted /dev/md/azure-ephemeral-md_0 at /mnt with fs=xfs chunk=512K count=${#NVME_DISKS[@]}" 0
}

test_nvme_aggregation_without_managed_resource() {
    configure_scsi_resource_disk 0
    configure_nvme_disks 2
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"

    run_and_assert "Mounted /dev/md/azure-ephemeral-md_0 at /mnt with fs=xfs chunk=512K count=2" 0
}

test_nvme_aggregation_with_managed_resource() {
    configure_scsi_resource_disk 1
    configure_nvme_disks 2
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"

    run_and_assert "Mounted /dev/md/azure-ephemeral-md_0 at /mnt with fs=xfs chunk=512K count=2" 0
}

test_nvme_already_formatted() {
    mkfs.ext4 -q -F "${NVME_DISKS[0]}"

    configure_scsi_resource_disk 0
    configure_nvme_disks 1
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"

    run_and_assert "Device ${NVME_DISKS[0]} contains a partition table or is already formatted" 1
}

test_nvme_already_mounted() {
    mkfs.ext4 -q -F "${NVME_DISKS[0]}"
    mount "${NVME_DISKS[0]}" /media

    configure_scsi_resource_disk 0
    configure_nvme_disks 1
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"

    run_and_assert "Device ${NVME_DISKS[0]} is already mounted or in use" 1
}

test_nvme_already_partitioned_multiple_unformatted() {
    parted -s "${NVME_DISKS[0]}" mklabel gpt mkpart primary ext4 0% 50%
    parted -s "${NVME_DISKS[0]}" mkpart primary ext4 50% 100%
    partprobe_safe

    configure_scsi_resource_disk 0
    configure_nvme_disks 1

    run_and_assert "Device ${NVME_DISKS[0]} has 2 partition(s)" 1
    assert_regex_in_log "Ignoring ${NVME_DISKS[0]}-part1, looks like a partition"
    assert_regex_in_log "Ignoring ${NVME_DISKS[0]}-part2, looks like a partition"
}

test_nvme_already_partitioned_multiple_formatted() {
    parted -s "${NVME_DISKS[0]}" mklabel gpt mkpart primary ext4 0% 50%
    parted -s "${NVME_DISKS[0]}" mkpart primary ext4 50% 100%
    partprobe_safe
    mkfs.ext4 -q -F "${NVME_DISKS[0]}-part1"
    mkfs.ext4 -q -F "${NVME_DISKS[0]}-part2"

    configure_scsi_resource_disk 0
    configure_nvme_disks 1

    run_and_assert "Device ${NVME_DISKS[0]} has 2 partition(s)" 1
    assert_regex_in_log "Ignoring ${NVME_DISKS[0]}-part1, looks like a partition"
    assert_regex_in_log "Ignoring ${NVME_DISKS[0]}-part2, looks like a partition"
}

test_nvme_already_partitioned_single_unformatted() {
    parted -s "${NVME_DISKS[0]}" mklabel gpt mkpart primary ext4 0% 100%
    partprobe_safe

    configure_scsi_resource_disk 0
    configure_nvme_disks 1

    run_and_assert "Device ${NVME_DISKS[0]} has 1 partition(s)" 1
    assert_regex_in_log "Ignoring ${NVME_DISKS[0]}-part1, looks like a partition"
}

test_nvme_already_partitioned_single_and_formatted() {
    parted -s "${NVME_DISKS[0]}" mklabel gpt mkpart primary ext4 0% 100%
    partprobe_safe
    mkfs.ext4 -q -F "${NVME_DISKS[0]}-part1"

    configure_scsi_resource_disk 0
    configure_nvme_disks 1

    run_and_assert "Device ${NVME_DISKS[0]} has 1 partition(s)" 1
}

test_nvme_single() {
    configure_scsi_resource_disk 0
    configure_nvme_disks 1
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"

    run_and_assert "Mounted ${NVME_DISKS[0]} at /mnt with fs=xfs" 0
}

test_nvme_single_and_managed_resource() {
    configure_scsi_resource_disk 1
    configure_nvme_disks 1
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"

    run_and_assert "Mounted ${NVME_DISKS[0]} at /mnt with fs=xfs" 0
}

test_nvme_single_and_unmanaged_resource() {
    configure_scsi_resource_disk 1
    configure_nvme_disks 1
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=false"

    run_and_assert "Mounted ${NVME_DISKS[0]} at /mnt with fs=xfs" 0
}

test_resource_managed() {
    configure_scsi_resource_disk 1
    configure_nvme_disks 0
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"

    run_and_assert "Mounted /dev/disk/azure/resource at /mnt with fs=xfs" 0
}

test_resource_unmanaged() {
    configure_scsi_resource_disk 1
    configure_nvme_disks 0
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=false"

    run_and_assert "No local NVMe disks detected and AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=false, exiting without action" 0
}

test_resource_with_extra_directory() {
    mount "${RESOURCE_DISK}-part1" /mnt
    mkdir /mnt/baddir
    umount /mnt

    configure_scsi_resource_disk 1
    configure_nvme_disks 0
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"

    run_and_assert "SCSI resource disk /dev/disk/azure/resource is NTFS formatted but contains unexpected files or folders: baddir" 1
}

test_resource_with_extra_file() {
    mount "${RESOURCE_DISK}-part1" /mnt
    touch /mnt/badfile.txt
    umount /mnt

    configure_scsi_resource_disk 1
    configure_nvme_disks 0
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"

    run_and_assert "SCSI resource disk /dev/disk/azure/resource is NTFS formatted but contains unexpected files or folders: badfile.txt" 1
}

test_resource_already_formatted_non_ntfs() {
    reset_disk "$RESOURCE_DISK"
    partprobe_safe
    mkfs.ext4 -q -F "$RESOURCE_DISK"

    configure_scsi_resource_disk 1
    configure_nvme_disks 0
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"

    run_and_assert "Device /dev/disk/azure/resource contains a partition table or is already formatted" 1
}

test_resource_already_formatted_ntfs_without_partition() {
    reset_disk "$RESOURCE_DISK"
    partprobe_safe
    mkfs.ntfs -q --quick --force "${RESOURCE_DISK}"

    configure_scsi_resource_disk 1
    configure_nvme_disks 0
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"

    run_and_assert "Device /dev/disk/azure/resource contains a partition table or is already formatted" 1
}

test_resource_already_mounted() {
    mkfs.ext4 -q -F "$RESOURCE_DISK"
    mount "$RESOURCE_DISK" /media

    configure_scsi_resource_disk 1
    configure_nvme_disks 0
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"

    run_and_assert "Device /dev/disk/azure/resource is already mounted or in use" 1
}

test_resource_already_partitioned_multiple() {
    parted -s "$RESOURCE_DISK" mklabel gpt mkpart primary ext4 0% 50%
    parted -s "$RESOURCE_DISK" mkpart primary ext4 50% 100%
    partprobe_safe

    configure_scsi_resource_disk 1
    configure_nvme_disks 0
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"

    run_and_assert "Device /dev/disk/azure/resource has 2 partition(s)" 1
}

test_resource_already_partitioned_single_formatted() {
    mkfs.ext4 -q -F "${RESOURCE_DISK}-part1"

    configure_scsi_resource_disk 1
    configure_nvme_disks 0
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"

    local resolved="$(readlink -f "${RESOURCE_DISK}-part1")"
    run_and_assert "Mounting ${resolved} as NTFS failed" 1
}

test_resource_unformatted() {
    reset_disk "$RESOURCE_DISK"
    partprobe_safe

    configure_scsi_resource_disk 1
    configure_nvme_disks 0
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"

    run_and_assert "Mounted /dev/disk/azure/resource at /mnt with fs=xfs" 0
}

run_tests() {
    SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
    TESTS=$(grep -Eo '^test_[a-zA-Z0-9_]+\(\)' "$SCRIPT_PATH" | sed 's/()//' | paste -sd' ' -)
    TEST_COUNT=0
    for TEST in $TESTS; do
        TEST_COUNT=$((TEST_COUNT + 1))
        reset
        echo "Running test #$TEST_COUNT: $TEST"
        $TEST
    done
}

run_tests
echo "All tests passed!"