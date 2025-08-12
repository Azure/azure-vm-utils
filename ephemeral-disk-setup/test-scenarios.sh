#!/bin/bash

###########################################################################
# Test scenarios for azure-ephemeral-disk-setup service.
#
# This script is designed to test the behavior of the azure-ephemeral-disk-setup
# script under various conditions, simulating different disk configurations
# and ensuring that it behaves correctly in each case.
#
# This is meant to be run on Standard_L32s_v3 which features SCSI resource and
# local NVMe disks (v1).
#
# Dependencies:
# sudo dnf install -y mdadm xfsprogs parted ntfsprogs ntfs-3g
#
###########################################################################

set -euo pipefail
shopt -s nullglob

RUN_LOG_STDOUT="/tmp/azure-ephemeral-test.0.stdout"
RUN_LOG_STDERR="/tmp/azure-ephemeral-test.0.stderr"

# Ensure the script is run as root
if [[ $EUID -ne 0 ]]; then
    echo "This script must be run as root" >&2
    exit 1
fi

# Ensure disks are symlinked correctly if previous runs deleted them.
rm -f /etc/udev/rules.d/66-azure-ephemeral.rules

# Scan NVMe disks.
mapfile -t NVME_DISKS < <(lsblk --paths --noheadings -nodeps -o NAME,MODEL | awk '$0 ~ /Microsoft NVMe Direct Disk( v2)?[[:space:]]*$/ {print $1}' | sort -V || true)

# Scan NVMe PCI addresses corresponding to the disks.
mapfile -t NVME_DISKS_PCI_ADDR < <(
    for disk in "${NVME_DISKS[@]}"; do
        # Resolve symlink to actual device
        actual_device="$(readlink -f "$disk")"
        # Extract nvme device name (e.g., nvme0 from /dev/nvme0n1)
        nvme_device="$(basename "$actual_device" | sed 's/n[0-9]*$//')"
        # Get PCI address from sysfs
        [[ -e "/sys/class/nvme/$nvme_device/device" ]] || exit 1
        pci_addr="$(basename "$(readlink -f "/sys/class/nvme/$nvme_device/device")")"
        echo "$pci_addr"
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
RESOURCE_DISK_RESOLVED="$(readlink -f "$RESOURCE_DISK")"
RESOURCE_DISK_PART1_RESOLVED="${RESOURCE_DISK_RESOLVED}1"
echo "Detected SCSI resource disk: $RESOURCE_DISK_PART1_RESOLVED"

# Scrub /etc/fstab to remove any lines with 'comment=' then save a backup.
chattr -i /etc/fstab
sed -i "/comment=/d" /etc/fstab
FSTAB_SAVED_PATH="/etc/fstab.saved"
cp /etc/fstab "$FSTAB_SAVED_PATH"

WAAGENT_CONF_SAVED_PATH="/etc/waagent.conf.saved"
cp /etc/waagent.conf "$WAAGENT_CONF_SAVED_PATH"

# Allow for hiding mdadm/mkfs.xfs tools to test failure cases.
MDADM_PATH="$(command -v mdadm)"
MDADM_SAVED_PATH="$MDADM_PATH.saved"
MKFS_XFS_PATH="$(command -v mkfs.xfs)"
MKFS_XFS_SAVED_PATH="MKFS_XFS_PATH.saved"

# Create a temporary directory for fake binaries to mock tools.
FAKE_BIN_PATH="$(mktemp -d)"
PATH="$FAKE_BIN_PATH:$PATH"

# Use full path to systemctl to avoid conflicts with faked systemctl under some tests.
SYSTEMCTL="$(command -v systemctl)"
MOUNT="$(command -v mount)"

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
    # Dynamically binds/unbinds NVMe devices via PCI to control which disks are available.
    local nvme_count=${#NVME_DISKS[@]}
    local desired_count="${1:-$nvme_count}"

    local i
    for i in $(seq 0 $(("${#NVME_DISKS[@]}" - 1))); do
        local pci_addr="${NVME_DISKS_PCI_ADDR[$i]}"

        if [[ $i -ge $desired_count ]]; then
            # Unbind the NVMe device to hide it
            if [[ -d "/sys/bus/pci/drivers/nvme/$pci_addr" ]]; then
                echo "$pci_addr" > /sys/bus/pci/drivers/nvme/unbind 2>/dev/null || true
                udevadm settle 2>/dev/null || true
            fi

            # Remove symlink if it exists
            rm -f "${NVME_DISKS[$i]}"
        else
            # Bind the NVMe device to make it available
            if [[ ! -d "/sys/bus/pci/drivers/nvme/$pci_addr" ]]; then
                echo "$pci_addr" > /sys/bus/pci/drivers/nvme/bind 2>/dev/null || true
                udevadm settle 2>/dev/null || true
            fi

            # Verify symlink exists after binding
            if [[ ! -b "${NVME_DISKS[$i]}" ]]; then
                echo "configure_nvme_disks: unexpected missing disk symlink ${NVME_DISKS[$i]} after binding $pci_addr"
                exit 1
            fi
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
    udevadm settle
}

fstab_add_entry() {
    echo "$1" >>/etc/fstab
    $SYSTEMCTL daemon-reload
}

mount_safe() {
    local device="$1"
    local target="$2"
    local systemd_mount_name
    systemd_mount_name="$(systemd-escape -p --suffix=mount "$target")"

    #echo "Mounting $device at $target with fs=$(blkid -o value -s TYPE "$device")" >&2
    $MOUNT "$device" "$target" >&2
    $SYSTEMCTL daemon-reload
    $SYSTEMCTL reset-failed "$systemd_mount_name" >&2
}

unmount_safe() {
    local target="$1"
    local systemd_mount_name
    systemd_mount_name="$(systemd-escape -p --suffix=mount "$target")"

    #echo "Unmounting $target with fs=$(findmnt --noheadings --output FSTYPE --target "$target")" >&2
    local umount_target="true"
    if $SYSTEMCTL status "$systemd_mount_name" >/dev/null 2>&1; then
        $SYSTEMCTL stop "$systemd_mount_name" >/dev/null 2>&1 && umount_target="false"
    fi

    if [[ "$umount_target" == "true" ]]; then
        umount "$target" >&2
    fi
    $SYSTEMCTL daemon-reload
}

reset_disk() {
    wipefs -q -a "$1" >/dev/null 2>&1 || true
}

reset_disks() {
    if findmnt /mnt >/dev/null 2>&1; then
        unmount_safe  /mnt
    fi

    local disk
    for disk in /dev/md/*; do
        local target
        target="$(findmnt --noheadings --output TARGET --source "$disk" || true)"
        if [[ -n "$target" ]]; then
            unmount_safe  "$target"
        fi
        reset_disk "$disk"
        mdadm -q --stop "$disk"
    done

    for disk in "${NVME_DISKS[@]}" "$RESOURCE_DISK" "${RESOURCE_DISK_PART1_RESOLVED}"; do
        if [[ ! -b "$disk" ]]; then
            continue
        fi

        local target
        target="$(findmnt --noheadings --output TARGET --source "$disk" || true)"
        if [[ -n "$target" ]]; then
            unmount_safe  "$target"
        fi
        reset_disk "$disk"
    done
    partprobe_safe

    configure_nvme_disks ${#NVME_DISKS[@]}
    configure_scsi_resource_disk 1

    if [[ -b "$RESOURCE_DISK" ]]; then
        reset_ntfs_resource_disk
    fi

    $SYSTEMCTL daemon-reload
    $SYSTEMCTL reset-failed || true
}

reset_fake_bin_dir() {
    rm -rf "${FAKE_BIN_PATH:?}"/*
}

reset_fstab() {
    chattr -i /etc/fstab
    cp "$FSTAB_SAVED_PATH" /etc/fstab
}

reset_waagent_conf() {
    cp "$WAAGENT_CONF_SAVED_PATH" /etc/waagent.conf
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
    mkfs.ntfs -q --quick "${RESOURCE_DISK_PART1_RESOLVED}" --label "Temporary Storage"
    mount_safe "${RESOURCE_DISK_PART1_RESOLVED}" /mnt
    echo "This is a test NTFS file" >/mnt/dataloss_warning_readme.txt
    unmount_safe  /mnt
}

reset_all() {
    #echo "Resetting all state..." >&2
    reset_fake_bin_dir
    reset_fstab
    reset_mdadm
    reset_mkfs_xfs
    reset_disks
    reset_waagent_conf
    configure_conf
    chmod 755 /mnt
}

on_exit() {
    echo "Cleaning up for exit..."
    if findmnt /mnt >/dev/null 2>&1; then
        unmount_safe  /mnt
    fi

    reset_all
    partprobe_safe
}
trap on_exit EXIT INT TERM

assert_in_stderr() {
    local expected_string="$1"

    if ! grep -q -F "$expected_string" "$RUN_LOG_STDERR"; then
        echo "❌ $TEST_COUNT $TEST LOG ASSERTION FAILED: Expected \"$expected_string\""
        exit 1
    fi
}

assert_regex_in_stderr() {
    local expected_regex="$1"

    if ! grep -q "$expected_regex" "$RUN_LOG_STDERR"; then
        echo "❌ $TEST_COUNT $TEST LOG ASSERTION FAILED: Expected \"$expected_regex\""
        exit 1
    fi
}

run_and_assert() {
    local expected_output="$1"
    local expected_code="$2"
    local regex="${3:-false}"

    local actual_output
    local actual_code=0

    RUN_LOG_STDOUT="/tmp/azure-ephemeral-test.$TEST_COUNT.stdout"
    RUN_LOG_STDERR="/tmp/azure-ephemeral-test.$TEST_COUNT.stderr"

    azure-ephemeral-disk-setup >"$RUN_LOG_STDOUT" 2>"$RUN_LOG_STDERR" || actual_code=$?
    actual_output="$(cat "$RUN_LOG_STDOUT")"

    if [[ "$regex" == "true" && ! "$actual_output" =~ $expected_output ]]; then
        echo "❌ $TEST_COUNT $TEST OUTPUT FAILED: Actual \"$actual_output\" !~ Expected \"$expected_output\""
        exit 1
    elif [[ "$regex" == "false" && "$actual_output" != "$expected_output" ]]; then
        echo "❌ $TEST_COUNT $TEST OUTPUT FAILED: Actual \"$actual_output\" != Expected \"$expected_output\""
        exit 1
    fi

    if [[ $actual_code -ne $expected_code ]]; then
        echo "❌ $TEST_COUNT $TEST EXIT CODE FAILED: Actual code=$actual_code != Expected code=$expected_code"
        exit 1
    fi

    echo "✅ $TEST_COUNT $TEST: $actual_output (code=$actual_code)"
}

fake_mount_that_fails_first_call() {
    # Creates a fake mount command that fails the first call, simulating a mount failure, then passes through subsequent calls.
    cat <<EOF > "$FAKE_BIN_PATH/mount"
#!/bin/bash -x
called_path="$FAKE_BIN_PATH/mount_called"
[[ -f \$called_path ]] && exec /usr/bin/mount "\$@"
touch "\$called_path"
exit 1
EOF
    chmod +x "$FAKE_BIN_PATH/mount"
    hash -r
}

fake_mount_that_fails_ntfs_and_ntfs3_with_unknown_filesystem() {
    # Creates a fake mount command that fails with "unknown filesystem type" for ntfs and ntfs3.
    cat <<EOF > "$FAKE_BIN_PATH/mount"
#!/bin/bash -x
[[ "\$2" == "ntfs" || "\$2" == "ntfs3" ]] || exec /usr/bin/mount "\$@"
echo "mount: unknown filesystem type '\$2'" >&2
exit 32
EOF

    chmod +x "$FAKE_BIN_PATH/mount"
    hash -r
}

fake_systemctl_that_hangs_on_start() {
    # Create a systemctl that hangs on "start" calls but passes through other commands.
    cat <<EOF > "$FAKE_BIN_PATH/systemctl"
#!/bin/bash
echo "fake systemctl called with args: \$@" >&2
[[ "\$1" == "start" ]] || exec /usr/bin/systemctl "\$@"
sleep 1000
EOF
    chmod +x "$FAKE_BIN_PATH/systemctl"
    hash -r
}

fake_systemctl_that_fails_on_start() {
    # Create a systemctl that fails on "start" calls but passes through other commands.
    cat <<EOF > "$FAKE_BIN_PATH/systemctl"
#!/bin/bash
echo "fake systemctl called with args: \$@" >&2
[[ "\$1" == "start" ]] || exec /usr/bin/systemctl "\$@"
exit 1
EOF
    chmod +x "$FAKE_BIN_PATH/systemctl"
    hash -r
}

run_and_assert_success() {
    local expected_output="$1"
    run_and_assert "$expected_output" 0
}

run_and_assert_failure() {
    local expected_output="$1"
    run_and_assert "$expected_output" 1
}

run_and_assert_failure_regex() {
    local expected_output="$1"
    run_and_assert "$expected_output" 1 true
}

test_load_config() {
    configure_nvme_disks 0
    configure_scsi_resource_disk 0

    cat >/etc/azure-ephemeral-disk-setup.conf <<EOF
######
# Configuration for azure-ephemeral-disk-setup.service
##

# Aggregation mode to use if multiple NVMe disks are found: {mdadm, none}
# If set to 'mdadm', multiple local NVMe disks will be aggregated into a single raid0 array.
# If set to 'none', at most one disk will be used.
AZURE_EPHEMERAL_DISK_SETUP_AGGREGATION=mdadm

# Filesystem type: {ext4, xfs}
AZURE_EPHEMERAL_DISK_SETUP_FS_TYPE=ext4

# mdadm chunk size: must be a positive integer followed by K, M, G, or T (e.g., 512K, 1M, 2G)
AZURE_EPHEMERAL_DISK_SETUP_MDADM_CHUNK=512K

# mdadm array name: must be alphanumeric, underscores, or hyphens
AZURE_EPHEMERAL_DISK_SETUP_MDADM_NAME=azure-ephemeral-md

# Target mount point for ephemeral disks: must be absolute path with no spaces
AZURE_EPHEMERAL_DISK_SETUP_MOUNT_POINT=/mnt

# Manage SCSI resource disk: {true, false}
AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=false

  AZURE_EPHEMERAL_DISK_SETUP_MDADM_NAME = spacesallaround
  AZURE_EPHEMERAL_DISK_SETUP_MDADM_NAME = "spacesallaroundx2"
  AZURE_EPHEMERAL_DISK_SETUP_MDADM_NAME = 'spacesallaroundx3'

AZURE_EPHEMERAL_DISK_SETUP_MDADM_NAME=foo
AZURE_EPHEMERAL_DISK_SETUP_MDADM_NAME="foox2"
AZURE_EPHEMERAL_DISK_SETUP_MDADM_NAME='foox3'

IGNORED1
IGNORED2=
IGNORED3=FOO
EOF

    run_and_assert_success "No local NVMe disks detected, exiting without action"

    assert_in_stderr "Configuration file set key=AZURE_EPHEMERAL_DISK_SETUP_AGGREGATION with value=mdadm"
    assert_in_stderr "Configuration file set key=AZURE_EPHEMERAL_DISK_SETUP_FS_TYPE with value=ext4"
    assert_in_stderr "Configuration file set key=AZURE_EPHEMERAL_DISK_SETUP_MDADM_CHUNK with value=512K"
    assert_in_stderr "Configuration file set key=AZURE_EPHEMERAL_DISK_SETUP_MDADM_NAME with value=azure-ephemeral-md"
    assert_in_stderr "Configuration file set key=AZURE_EPHEMERAL_DISK_SETUP_MOUNT_POINT with value=/mnt"
    assert_in_stderr "Configuration file set key=AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE with value=false"
    assert_in_stderr "WARNING: ignoring invalid config key=IGNORED1"
    assert_in_stderr "WARNING: ignoring invalid config key=IGNORED2"
    assert_in_stderr "WARNING: ignoring invalid config key=IGNORED3"
    assert_in_stderr "Configuration file set key=AZURE_EPHEMERAL_DISK_SETUP_MDADM_NAME with value=spacesallaround"
    assert_in_stderr "Configuration file set key=AZURE_EPHEMERAL_DISK_SETUP_MDADM_NAME with value=spacesallaroundx2"
    assert_in_stderr "Configuration file set key=AZURE_EPHEMERAL_DISK_SETUP_MDADM_NAME with value=spacesallaroundx3"
    assert_in_stderr "Configuration file set key=AZURE_EPHEMERAL_DISK_SETUP_MDADM_NAME with value=foo"
    assert_in_stderr "Configuration file set key=AZURE_EPHEMERAL_DISK_SETUP_MDADM_NAME with value=foox2"
    assert_in_stderr "Configuration file set key=AZURE_EPHEMERAL_DISK_SETUP_MDADM_NAME with value=foox3"
}

test_configured_but_not_yet_mounted() {
    configure_nvme_disks 1
    configure_scsi_resource_disk 0
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"

    fstab_add_entry "LABEL=AzureEphmDsk /mnt ext4 defaults,nofail,comment=azure-ephemeral-disk-setup 0 2"
    mkfs.ext4 -q -F "${NVME_DISKS[0]}" -L AzureEphmDsk

    run_and_assert_success "Mount point /mnt is mounted and ready for use"
    assert_in_stderr "Mount point /mnt is configured in /etc/fstab but not mounted, waiting for mnt.mount..."
}

test_configured_but_not_yet_mounted_systemctl_wait_timeout_falls_back_to_mount() {
    configure_nvme_disks 1
    configure_scsi_resource_disk 0
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SYSTEMD_UNIT_TIMEOUT_SECS=5"

    fstab_add_entry "LABEL=AzureEphmDsk /mnt ext4 defaults,nofail,comment=azure-ephemeral-disk-setup 0 2"
    mkfs.ext4 -q -F "${NVME_DISKS[0]}" -L AzureEphmDsk

    fake_systemctl_that_hangs_on_start

    run_and_assert_success "Mount point /mnt is mounted and ready for use"
    assert_in_stderr "Mount point /mnt is configured in /etc/fstab but not mounted, waiting for mnt.mount..."
    assert_in_stderr "Timed out waiting for systemd unit mnt.mount to become active"
}

test_configured_but_not_yet_mounted_systemd_unit_timeout_and_mount_fails_fresh() {
    configure_nvme_disks 1
    configure_scsi_resource_disk 0
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SYSTEMD_UNIT_TIMEOUT_SECS=5"

    fstab_add_entry "LABEL=AzureEphmDsk /mnt ext4 defaults,nofail,comment=azure-ephemeral-disk-setup 0 2"

    fake_mount_that_fails_first_call
    fake_systemctl_that_hangs_on_start

    run_and_assert_success "Mounted /dev/nvme0n1 at /mnt with fs=ext4"
    assert_in_stderr "Mount point /mnt is configured in /etc/fstab but not mounted, waiting for mnt.mount..."
    assert_in_stderr "Timed out waiting for systemd unit mnt.mount to become active"
    assert_in_stderr "Failed to start existing mount for /mnt"
}

test_configured_but_not_yet_mounted_systemd_unit_timeout_and_mount_fails_already_setup() {
    configure_nvme_disks 1
    configure_scsi_resource_disk 0
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SYSTEMD_UNIT_TIMEOUT_SECS=5"

    fstab_add_entry "LABEL=AzureEphmDsk /mnt ext4 defaults,nofail,comment=azure-ephemeral-disk-setup 0 2"
    mkfs.ext4 -q -F "${NVME_DISKS[0]}" -L AzureEphmDsk

    fake_mount_that_fails_first_call
    fake_systemctl_that_hangs_on_start

    run_and_assert_failure "Device /dev/nvme0n1 contains a partition table or is already formatted"
    assert_in_stderr "Mount point /mnt is configured in /etc/fstab but not mounted, waiting for mnt.mount..."
    assert_in_stderr "Timed out waiting for systemd unit mnt.mount to become active"
    assert_in_stderr "Failed to start existing mount for /mnt"
}

test_resource_configured_via_cloudinit_but_not_yet_mounted_setup_scsi_resource_false() {
    configure_nvme_disks 1
    configure_scsi_resource_disk 1
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=false"

    fstab_add_entry "/dev/disk/cloud/azure_resource-part1    /mnt    auto    defaults,nofail,comment=cloudconfig     0       2"
    mkfs.ext4 -q -F "/dev/disk/cloud/azure_resource-part1"

    run_and_assert_success "Mount point /mnt is already configured by cloud-init and AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=false, nothing to do"
}

test_resource_configured_via_cloudinit_but_not_yet_mounted_setup_scsi_resource_true() {
    configure_nvme_disks 1
    configure_scsi_resource_disk 1
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"

    fstab_add_entry "/dev/disk/cloud/azure_resource-part1    /mnt    auto    defaults,nofail,comment=cloudconfig     0       2"
    mkfs.ext4 -q -F "/dev/disk/cloud/azure_resource-part1"

    run_and_assert_failure "Mount point /mnt is already configured by cloud-init, but AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"
}

test_resource_configured_via_cloudinit_and_mounted_setup_scsi_resource_false() {
    configure_nvme_disks 1
    configure_scsi_resource_disk 1
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=false"

    fstab_add_entry "/dev/disk/cloud/azure_resource-part1    /mnt    auto    defaults,nofail,comment=cloudconfig     0       2"
    mkfs.ext4 -q -F "/dev/disk/cloud/azure_resource-part1"
    mount_safe /dev/disk/cloud/azure_resource-part1 /mnt

    run_and_assert_success "Mount point /mnt is already configured by cloud-init and AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=false, nothing to do"
}

test_resource_configured_via_cloudinit_and_mounted_setup_scsi_resource_true() {
    configure_nvme_disks 1
    configure_scsi_resource_disk 1
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"

    fstab_add_entry "/dev/disk/cloud/azure_resource-part1    /mnt    auto    defaults,nofail,comment=cloudconfig     0       2"
    mkfs.ext4 -q -F "/dev/disk/cloud/azure_resource-part1"
    mount_safe /dev/disk/cloud/azure_resource-part1 /mnt

    run_and_assert_failure "Mount point /mnt is already configured by cloud-init, but AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true" 1
}

test_conflict_with_walinuxagent() {
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"
    echo "ResourceDisk.Format=y" >>/etc/waagent.conf
    run_and_assert_failure "/etc/waagent.conf has ResourceDisk.Format=y which may conflict with this service"

    # Check with spaces.
    reset_waagent_conf
    echo "ResourceDisk.Format  =  y" >>/etc/waagent.conf
    run_and_assert_failure "/etc/waagent.conf has ResourceDisk.Format=y which may conflict with this service"
}

test_reboot_systemctl_wait_single_nvme() {
    configure_nvme_disks 1
    configure_scsi_resource_disk 0

    run_and_assert_success "Mounted ${NVME_DISKS[0]} at /mnt with fs=ext4"

    # Simulate a reboot by resetting unmounting /mnt via systemd.
    $SYSTEMCTL stop mnt.mount

    run_and_assert_success "Mount point /mnt is mounted and ready for use"
    assert_in_stderr "Mount point /mnt is configured in /etc/fstab but not mounted, waiting for mnt.mount..."
}

test_reboot_systemctl_wait_aggregated_nvme() {
    configure_nvme_disks 2
    configure_scsi_resource_disk 0

    run_and_assert_success "Mounted /dev/md/azure-ephemeral-md_0 at /mnt with fs=ext4 chunk=512K count=2"

    # Simulate a reboot by resetting unmounting /mnt via systemd.
    $SYSTEMCTL stop mnt.mount

    run_and_assert_success "Mount point /mnt is mounted and ready for use"
    assert_in_stderr "Mount point /mnt is configured in /etc/fstab but not mounted, waiting for mnt.mount..."
}

test_reboot_systemctl_wait_managed_resource() {
    configure_nvme_disks 0
    configure_scsi_resource_disk 1
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"

    run_and_assert_success "Mounted /dev/disk/azure/resource at /mnt with fs=ext4"

    # Simulate a reboot by resetting unmounting /mnt via systemd.
    $SYSTEMCTL stop mnt.mount

    run_and_assert_success "Mount point /mnt is mounted and ready for use"
    assert_in_stderr "Mount point /mnt is configured in /etc/fstab but not mounted, waiting for mnt.mount..."
}

test_reboot_mount_fallback_single_nvme() {
    configure_nvme_disks 1
    configure_scsi_resource_disk 0
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SYSTEMD_UNIT_TIMEOUT_SECS=5"

    run_and_assert_success "Mounted ${NVME_DISKS[0]} at /mnt with fs=ext4"

    # Simulate a reboot by resetting unmounting /mnt.
    unmount_safe  /mnt
    fake_systemctl_that_fails_on_start

    run_and_assert_success "Mount point /mnt is mounted and ready for use"
    assert_in_stderr "Mount point /mnt is configured in /etc/fstab but not mounted, waiting for mnt.mount..."
    assert_regex_in_stderr "^+ mount --target /mnt$"
}

test_reboot_mount_fallback_aggregated_nvme() {
    configure_nvme_disks 2
    configure_scsi_resource_disk 0
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SYSTEMD_UNIT_TIMEOUT_SECS=5"

    run_and_assert_success "Mounted /dev/md/azure-ephemeral-md_0 at /mnt with fs=ext4 chunk=512K count=2"

    # Simulate a reboot by resetting unmounting /mnt.
    unmount_safe  /mnt
    fake_systemctl_that_fails_on_start

    run_and_assert_success "Mount point /mnt is mounted and ready for use"
    assert_in_stderr "Mount point /mnt is configured in /etc/fstab but not mounted, waiting for mnt.mount..."
    assert_regex_in_stderr "^+ mount --target /mnt$"
}

test_reboot_mount_fallback_managed_resource() {
    configure_nvme_disks 0
    configure_scsi_resource_disk 1
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true" "AZURE_EPHEMERAL_DISK_SETUP_SYSTEMD_UNIT_TIMEOUT_SECS=5"

    run_and_assert_success "Mounted /dev/disk/azure/resource at /mnt with fs=ext4"

    # Simulate a reboot by resetting unmounting /mnt.
    unmount_safe  /mnt
    fake_systemctl_that_fails_on_start

    run_and_assert_success "Mount point /mnt is mounted and ready for use"
    assert_in_stderr "Mount point /mnt is configured in /etc/fstab but not mounted, waiting for mnt.mount..."
    assert_regex_in_stderr "^+ mount --target /mnt$"
}

test_resource_managed_missing_ntfs_drivers() {
    configure_nvme_disks 0
    configure_scsi_resource_disk 1
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"

    fake_mount_that_fails_ntfs_and_ntfs3_with_unknown_filesystem

    run_and_assert_success "Mounted /dev/disk/azure/resource at /mnt with fs=ext4"
    assert_in_stderr "WARNING: failed to mount $RESOURCE_DISK_PART1_RESOLVED due to lack of ntfs support, assuming it is empty and safe for reformat"
}

test_format_failure_single_nvme() {
    configure_nvme_disks 1
    configure_scsi_resource_disk 0

    cp /bin/false "$FAKE_BIN_PATH/mkfs.ext4"
    hash -r

    run_and_assert_failure "Formatting ${NVME_DISKS[0]} failed"
}

test_format_failure_aggregated_nvme() {
    configure_nvme_disks 2
    configure_scsi_resource_disk 0

    cp /bin/false "$FAKE_BIN_PATH/mkfs.ext4"
    hash -r

    run_and_assert_failure "Formatting /dev/md/azure-ephemeral-md_0 failed"
}

test_format_failure_scsi_resource() {
    configure_nvme_disks 0
    configure_scsi_resource_disk 1
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"

    cp /bin/false "$FAKE_BIN_PATH/mkfs.ext4"
    hash -r

    run_and_assert_failure "Formatting /dev/disk/azure/resource failed"
}

test_idempotent_rerun() {
    configure_nvme_disks 1
    configure_scsi_resource_disk 0

    run_and_assert_success "Mounted ${NVME_DISKS[0]} at /mnt with fs=ext4"
    run_and_assert_success "Mount point /mnt is mounted and ready for use"
}

test_fstab_readonly() {
    configure_nvme_disks 1
    configure_scsi_resource_disk 0

    disable_write_fstab

    run_and_assert_success "Mounted ${NVME_DISKS[0]} at /mnt with fs=ext4"
    assert_in_stderr "WARNING: unable to persist mount to /etc/fstab"
}

test_fstab_readonly_reboot_single_nvme() {
    configure_nvme_disks 1
    configure_scsi_resource_disk 0
    configure_conf

    disable_write_fstab

    run_and_assert_success "Mounted ${NVME_DISKS[0]} at /mnt with fs=ext4"
    assert_in_stderr "WARNING: unable to persist mount to /etc/fstab"

    # Simulate a reboot by resetting unmounting /mnt.
    unmount_safe  /mnt

    run_and_assert_success "Mounted existing filesystem with label=AzureEphmDsk at /mnt without fstab entry"
}

test_fstab_readonly_reboot_already_mounted_elsewhere() {
    configure_nvme_disks 1
    configure_scsi_resource_disk 0

    disable_write_fstab

    run_and_assert_success "Mounted ${NVME_DISKS[0]} at /mnt with fs=ext4"
    assert_in_stderr "WARNING: unable to persist mount to /etc/fstab"

    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_MOUNT_POINT=/media"
    run_and_assert_failure_regex "Filesystem with label=AzureEphmDsk is unexpectedly mounted: ${NVME_DISKS[0]}[[:space:]]+/mnt[[:space:]]+ext4[[:space:]]+rw,relatime,stripe=[0-9]+[[:space:]]+AzureEphmDsk"
}

test_fstab_readonly_reboot_aggregated_nvme() {
    configure_nvme_disks 2
    configure_scsi_resource_disk 0

    disable_write_fstab

    run_and_assert_success "Mounted /dev/md/azure-ephemeral-md_0 at /mnt with fs=ext4 chunk=512K count=2"
    assert_in_stderr "WARNING: unable to persist mount to /etc/fstab"

    # Simulate a reboot by resetting unmounting /mnt.
    unmount_safe  /mnt

    run_and_assert_success "Mounted existing filesystem with label=AzureEphmDsk at /mnt without fstab entry"
    assert_in_stderr "WARNING: found existing filesystem with label=AzureEphmDsk but no fstab entry configured: /dev/md"
}

test_fstab_readonly_idempotent_single_nvme() {
    configure_nvme_disks 1
    configure_scsi_resource_disk 0

    disable_write_fstab

    run_and_assert_success "Mounted ${NVME_DISKS[0]} at /mnt with fs=ext4"
    assert_in_stderr "WARNING: unable to persist mount to /etc/fstab"

    run_and_assert_success "Mount point /mnt is mounted and ready for use"
}

test_fstab_readonly_idempotent_aggregated_nvme() {
    configure_nvme_disks 2
    configure_scsi_resource_disk 0

    disable_write_fstab

    run_and_assert_success "Mounted /dev/md/azure-ephemeral-md_0 at /mnt with fs=ext4 chunk=512K count=2"

    if ! grep -q "WARNING: unable to persist mount to /etc/fstab" "$RUN_LOG_STDERR"; then
        echo "Expected warning about fstab not being writable was not found in log"
        exit 1
    fi

    run_and_assert_success "Mount point /mnt is mounted and ready for use"
}

test_fstab_conflicting_entry() {
    configure_nvme_disks 1
    configure_scsi_resource_disk 0

    fstab_add_entry "/dev/fake /mnt xfs defaults,comment=otherservice 0 2"

    run_and_assert_failure "Aborting due to conflicting fstab entry for /mnt with source=/dev/fake fstype=xfs options=defaults,comment=otherservice"
}

test_broken_symlink_resource() {
    configure_nvme_disks 0
    configure_scsi_resource_disk 1
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"

    ln -sf /dev/nonexistent /dev/disk/azure/resource

    run_and_assert_failure "Not a valid block device: /dev/disk/azure/resource"
}

test_custom_mount() {
    configure_nvme_disks 0
    configure_scsi_resource_disk 1
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true" 'AZURE_EPHEMERAL_DISK_SETUP_MOUNT_POINT=/mnt/custom-MOUNT_0'

    run_and_assert_success "Mounted /dev/disk/azure/resource at /mnt/custom-MOUNT_0 with fs=ext4"
}

test_custom_udevadm_settle_timeout() {
    configure_nvme_disks 0
    configure_scsi_resource_disk 1
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true" 'AZURE_EPHEMERAL_DISK_SETUP_UDEVADM_SETTLE_TIMEOUT_SECS=90'

    run_and_assert_success "Mounted /dev/disk/azure/resource at /mnt with fs=ext4"
    assert_in_stderr "Waiting for udev to settle (timeout=90s)..."
}

test_custom_mount_deep() {
    configure_nvme_disks 0
    configure_scsi_resource_disk 1
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true" "AZURE_EPHEMERAL_DISK_SETUP_MOUNT_POINT=/mnt/foo/BAR/custom_0"

    run_and_assert_success "Mounted /dev/disk/azure/resource at /mnt/foo/BAR/custom_0 with fs=ext4"
}

test_custom_mdadm_chunk() {
    configure_nvme_disks 2
    configure_scsi_resource_disk 0
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_MDADM_CHUNK=1024K"

    run_and_assert_success "Mounted /dev/md/azure-ephemeral-md_0 at /mnt with fs=ext4 chunk=1024K count=2"
}

test_custom_mdam_name() {
    configure_nvme_disks 2
    configure_scsi_resource_disk 0
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_MDADM_NAME=my_RAID-0"

    run_and_assert_success "Mounted /dev/md/my_RAID-0_0 at /mnt with fs=ext4 chunk=512K count=2"
}

test_custom_fs_xfs_single() {
    configure_nvme_disks 1
    configure_scsi_resource_disk 0
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_FS_TYPE=xfs"

    run_and_assert_success "Mounted ${NVME_DISKS[0]} at /mnt with fs=xfs"
}

test_custom_fs_xfs_aggregated() {
    configure_nvme_disks 2
    configure_scsi_resource_disk 0
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_FS_TYPE=xfs"

    run_and_assert_success "Mounted /dev/md/azure-ephemeral-md_0 at /mnt with fs=xfs chunk=512K count=2"
}

test_invalid_config_aggregation() {
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_AGGREGATION=invalid"
    run_and_assert_failure "AZURE_EPHEMERAL_DISK_SETUP_AGGREGATION must be either 'auto', 'mdadm' or 'none'."
}

test_invalid_config_fs_type() {
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_FS_TYPE=ntfs"
    run_and_assert_failure "AZURE_EPHEMERAL_DISK_SETUP_FS_TYPE must be either 'ext4' or 'xfs'."
}

test_invalid_config_mdadm_chunk() {
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_MDADM_CHUNK=invalid"
    run_and_assert_failure "AZURE_EPHEMERAL_DISK_SETUP_MDADM_CHUNK must be a positive integer followed by K, M, G, or T (e.g., 512K, 1M, 2G)."

    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_MDADM_CHUNK=100"
    run_and_assert_failure "AZURE_EPHEMERAL_DISK_SETUP_MDADM_CHUNK must be a positive integer followed by K, M, G, or T (e.g., 512K, 1M, 2G)."

    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_MDADM_CHUNK=100Q"
    run_and_assert_failure "AZURE_EPHEMERAL_DISK_SETUP_MDADM_CHUNK must be a positive integer followed by K, M, G, or T (e.g., 512K, 1M, 2G)."
}

test_invalid_config_mdadm_name() {
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_MDADM_NAME=invalid\ name"
    run_and_assert_failure "AZURE_EPHEMERAL_DISK_SETUP_MDADM_NAME must be a valid name (alphanumeric, underscores, or hyphens)."
}

test_invalid_config_mount_point_path() {
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_MOUNT_POINT=relative/path"
    run_and_assert_failure "AZURE_EPHEMERAL_DISK_SETUP_MOUNT_POINT must be an absolute path and can only contain alphanumeric characters, underscores, hyphens, and slashes."

    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_MOUNT_POINT=/mnt/spaced out"
    run_and_assert_failure "AZURE_EPHEMERAL_DISK_SETUP_MOUNT_POINT must be an absolute path and can only contain alphanumeric characters, underscores, hyphens, and slashes."

    IFS=' ' read -r -a chars <<< '! @ # $ % ^ & * ( ) + = { } [ ] ; : " '\'' | < > , ? ; :'
    for char in "${chars[@]}"; do
        configure_conf "AZURE_EPHEMERAL_DISK_SETUP_MOUNT_POINT=/mnt/invalid${char}char"
        run_and_assert_failure "AZURE_EPHEMERAL_DISK_SETUP_MOUNT_POINT must be an absolute path and can only contain alphanumeric characters, underscores, hyphens, and slashes."
    done
}

test_invalid_config_scsi_resource() {
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=invalid"
    run_and_assert_failure "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE must be either 'true' or 'false'"
}

test_invalid_udevadm_settle_timeout() {
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_UDEVADM_SETTLE_TIMEOUT_SECS=invalid"
    run_and_assert_failure "AZURE_EPHEMERAL_DISK_SETUP_UDEVADM_SETTLE_TIMEOUT_SECS must be a positive integer"

    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_UDEVADM_SETTLE_TIMEOUT_SECS=-1"
    run_and_assert_failure "AZURE_EPHEMERAL_DISK_SETUP_UDEVADM_SETTLE_TIMEOUT_SECS must be a positive integer"

    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_UDEVADM_SETTLE_TIMEOUT_SECS=0"
    run_and_assert_failure "AZURE_EPHEMERAL_DISK_SETUP_UDEVADM_SETTLE_TIMEOUT_SECS must be a positive integer"
}

test_invalid_systemd_unit_timeout() {
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SYSTEMD_UNIT_TIMEOUT_SECS=invalid"
    run_and_assert_failure "AZURE_EPHEMERAL_DISK_SETUP_SYSTEMD_UNIT_TIMEOUT_SECS must be a positive integer"

    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SYSTEMD_UNIT_TIMEOUT_SECS=-1"
    run_and_assert_failure "AZURE_EPHEMERAL_DISK_SETUP_SYSTEMD_UNIT_TIMEOUT_SECS must be a positive integer"

    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SYSTEMD_UNIT_TIMEOUT_SECS=0"
    run_and_assert_failure "AZURE_EPHEMERAL_DISK_SETUP_SYSTEMD_UNIT_TIMEOUT_SECS must be a positive integer"
}

test_missing_mkfs_xfs() {
    hide_mkfs_xfs
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_FS_TYPE=xfs"

    run_and_assert_failure "mkfs.xfs is not installed and is required for formatting"
}

test_aggregation_mdadm_missing_mdadm() {
    hide_mdadm
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_AGGREGATION=mdadm"

    run_and_assert_failure "mdadm is not installed and is required for disk aggregation"
}

test_aggregation_auto_missing_mdadm() {
    hide_mdadm
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_AGGREGATION=auto"
    configure_nvme_disks 2

    run_and_assert_success "Mounted ${NVME_DISKS[0]} at /mnt with fs=ext4"
    assert_regex_in_stderr "mdadm is not available, setting AZURE_EPHEMERAL_DISK_SETUP_AGGREGATION to 'none'"
}

test_aggregation_auto_with_mdadm() {
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_AGGREGATION=auto"
    configure_nvme_disks

    run_and_assert_success "Mounted /dev/md/azure-ephemeral-md_0 at /mnt with fs=ext4 chunk=512K count=${#NVME_DISKS[@]}"
    assert_regex_in_stderr "mdadm is available, setting AZURE_EPHEMERAL_DISK_SETUP_AGGREGATION to 'mdadm'"
}

test_aggregation_none_missing_mdadm() {
    hide_mdadm
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_AGGREGATION=none"
    configure_nvme_disks 2

    run_and_assert_success "Mounted ${NVME_DISKS[0]} at /mnt with fs=ext4"
}

test_mount_point_is_a_file() {
    configure_nvme_disks 1
    configure_scsi_resource_disk 0

    local temp_path
    temp_path="$(mktemp /tmp/XXXXXX)"
    configure_conf AZURE_EPHEMERAL_DISK_SETUP_MOUNT_POINT="$temp_path"

    run_and_assert_failure "Mount point $temp_path exists, but is not a directory"
    rm -f "$temp_path"
}

test_mount_point_is_a_symlink() {
    configure_nvme_disks 1
    configure_scsi_resource_disk 0

    local temp_path
    temp_path="$(mktemp /tmp/XXXXXX)"

    local temp_path2
    temp_path2="$(mktemp /tmp/XXXXXX)"

    ln -sf "$temp_path2" "$temp_path"
    configure_conf AZURE_EPHEMERAL_DISK_SETUP_MOUNT_POINT="$temp_path"

    run_and_assert_failure "Mount point $temp_path exists, but is not a directory"

    rm -f "$temp_path"
    rm -f "$temp_path2"
}

test_no_nvme_or_managed_resource_disks() {
    configure_nvme_disks 0
    configure_scsi_resource_disk 0
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"

    run_and_assert_success "No local NVMe or SCSI resource disks detected, exiting without action"
}

test_no_nvme_or_unmanaged_resource_disks() {
    configure_nvme_disks 0
    configure_scsi_resource_disk 0

    run_and_assert_success "No local NVMe disks detected, exiting without action"
}

test_nvme_aggregation_disabled() {
    configure_nvme_disks 2
    configure_scsi_resource_disk 0
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_AGGREGATION=none"

    run_and_assert_success "Mounted ${NVME_DISKS[0]} at /mnt with fs=ext4"
    assert_in_stderr "Multiple disks found but aggregation is disabled. Only using ${NVME_DISKS[0]}"
}

test_nvme_aggregation_max() {
    configure_nvme_disks ${#NVME_DISKS[@]}
    configure_scsi_resource_disk 0
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"

    run_and_assert_success "Mounted /dev/md/azure-ephemeral-md_0 at /mnt with fs=ext4 chunk=512K count=${#NVME_DISKS[@]}"
}

test_nvme_aggregation_max_with_managed_resource() {
    configure_nvme_disks ${#NVME_DISKS[@]}
    configure_scsi_resource_disk 1
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"

    run_and_assert_success "Mounted /dev/md/azure-ephemeral-md_0 at /mnt with fs=ext4 chunk=512K count=${#NVME_DISKS[@]}"
}

test_nvme_aggregation_without_managed_resource() {
    configure_nvme_disks 2
    configure_scsi_resource_disk 0
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"

    run_and_assert_success "Mounted /dev/md/azure-ephemeral-md_0 at /mnt with fs=ext4 chunk=512K count=2"
}

test_nvme_aggregation_with_managed_resource() {
    configure_nvme_disks 2
    configure_scsi_resource_disk 1
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"

    run_and_assert_success "Mounted /dev/md/azure-ephemeral-md_0 at /mnt with fs=ext4 chunk=512K count=2"
}

test_nvme_already_formatted() {
    configure_nvme_disks 1
    configure_scsi_resource_disk 0
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"

    mkfs.ext4 -q -F "${NVME_DISKS[0]}"

    run_and_assert_failure "Device ${NVME_DISKS[0]} contains a partition table or is already formatted"
}

test_nvme_already_mounted() {
    configure_nvme_disks 1
    configure_scsi_resource_disk 0
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"

    mkfs.ext4 -q -F "${NVME_DISKS[0]}"
    mount_safe "${NVME_DISKS[0]}" /media

    run_and_assert_failure "Device ${NVME_DISKS[0]} is already mounted or in use"
}

test_nvme_already_partitioned_multiple_unformatted() {
    parted -s "${NVME_DISKS[0]}" mklabel gpt mkpart primary ext4 0% 50%
    parted -s "${NVME_DISKS[0]}" mkpart primary ext4 50% 100%
    partprobe_safe

    configure_scsi_resource_disk 0
    configure_nvme_disks 1

    run_and_assert_failure "Device ${NVME_DISKS[0]} has 2 partition(s)"
}

test_nvme_already_partitioned_multiple_formatted() {
    parted -s "${NVME_DISKS[0]}" mklabel gpt mkpart primary ext4 0% 50%
    parted -s "${NVME_DISKS[0]}" mkpart primary ext4 50% 100%
    partprobe_safe
    mkfs.ext4 -q -F "${NVME_DISKS[0]}p1"
    mkfs.ext4 -q -F "${NVME_DISKS[0]}p2"

    configure_scsi_resource_disk 0
    configure_nvme_disks 1

    run_and_assert_failure "Device ${NVME_DISKS[0]} has 2 partition(s)"
}

test_nvme_already_partitioned_single_unformatted() {
    parted -s "${NVME_DISKS[0]}" mklabel gpt mkpart primary ext4 0% 100%
    partprobe_safe

    configure_scsi_resource_disk 0
    configure_nvme_disks 1

    run_and_assert_failure "Device ${NVME_DISKS[0]} has 1 partition(s)"
}

test_nvme_already_partitioned_single_and_formatted() {
    parted -s "${NVME_DISKS[0]}" mklabel gpt mkpart primary ext4 0% 100%
    partprobe_safe
    mkfs.ext4 -q -F "${NVME_DISKS[0]}p1"

    configure_scsi_resource_disk 0
    configure_nvme_disks 1

    run_and_assert_failure "Device ${NVME_DISKS[0]} has 1 partition(s)"
}

test_nvme_single() {
    configure_nvme_disks 1
    configure_scsi_resource_disk 0
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"

    run_and_assert_success "Mounted ${NVME_DISKS[0]} at /mnt with fs=ext4"
}

test_nvme_single_and_managed_resource() {
    configure_nvme_disks 1
    configure_scsi_resource_disk 1
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"

    run_and_assert_success "Mounted ${NVME_DISKS[0]} at /mnt with fs=ext4"
}

test_nvme_single_and_unmanaged_resource() {
    configure_nvme_disks 1
    configure_scsi_resource_disk 1
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=false"

    run_and_assert_success "Mounted ${NVME_DISKS[0]} at /mnt with fs=ext4"
}

test_resource_managed() {
    configure_nvme_disks 0
    configure_scsi_resource_disk 1
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"

    run_and_assert_success "Mounted /dev/disk/azure/resource at /mnt with fs=ext4"
}

test_resource_ntfs_wrong_label() {
    configure_nvme_disks 0
    configure_scsi_resource_disk 1
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"

    local label="NotTemporaryStorage"
    mkfs.ntfs -q --quick "$RESOURCE_DISK_PART1_RESOLVED" --label "$label"

    run_and_assert_failure "Resource disk partition $RESOURCE_DISK_PART1_RESOLVED has label=$label, expected label=Temporary Storage"
}

test_resource_unmanaged() {
    configure_nvme_disks 0
    configure_scsi_resource_disk 1
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=false"

    run_and_assert_success "No local NVMe disks detected and AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=false, exiting without action"
}

test_resource_already_mounted_by_cloudinit_scsi_setup_disabled() {
    configure_nvme_disks 1
    configure_scsi_resource_disk 1

    fstab_add_entry "/dev/disk/cloud/azure_resource-part1    /mnt    auto    defaults,nofail,comment=cloudconfig     0       2"
    mount_safe /dev/disk/cloud/azure_resource-part1 /mnt

    run_and_assert_success "Mount point /mnt is already configured by cloud-init and AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=false, nothing to do"
}


test_resource_already_mounted_by_cloudinit_scsi_setup_enabled() {
    configure_nvme_disks 1
    configure_scsi_resource_disk 1
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"

    fstab_add_entry "/dev/disk/cloud/azure_resource-part1    /mnt    auto    defaults,nofail,comment=cloudconfig     0       2"
    mount_safe /dev/disk/cloud/azure_resource-part1 /mnt

    run_and_assert_failure "Mount point /mnt is already configured by cloud-init, but AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"
}

test_resource_with_extra_directory() {
    mount_safe "${RESOURCE_DISK_PART1_RESOLVED}" /mnt
    mkdir /mnt/baddir
    unmount_safe  /mnt

    configure_scsi_resource_disk 1
    configure_nvme_disks 0
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"

    run_and_assert_failure "SCSI resource disk /dev/disk/azure/resource is NTFS formatted but contains unexpected files or folders: baddir"
}

test_resource_with_extra_file() {
    configure_nvme_disks 0
    configure_scsi_resource_disk 1
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"

    mount_safe "${RESOURCE_DISK_PART1_RESOLVED}" /mnt
    touch /mnt/badfile.txt
    unmount_safe  /mnt

    run_and_assert_failure "SCSI resource disk /dev/disk/azure/resource is NTFS formatted but contains unexpected files or folders: badfile.txt"
}

test_resource_already_formatted_non_ntfs() {
    configure_nvme_disks 0
    configure_scsi_resource_disk 1
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"

    mkfs.ext4 -q -F "${RESOURCE_DISK_PART1_RESOLVED}"

    run_and_assert_failure "Resource disk partition $RESOURCE_DISK_PART1_RESOLVED has type=ext4, expected type=ntfs"
}

test_resource_already_formatted_ntfs_without_partition() {
    configure_scsi_resource_disk 1
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"
    mkfs.ntfs -q --quick --force "${RESOURCE_DISK}" --label "Temporary Storage"
    partprobe_safe
    configure_nvme_disks 0

    run_and_assert_failure "Device /dev/disk/azure/resource contains a partition table or is already formatted"
}

test_resource_already_mounted_elsewhere() {
    configure_nvme_disks 0
    configure_scsi_resource_disk 1
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"

    $MOUNT -t ntfs "${RESOURCE_DISK_PART1_RESOLVED}" /media

    run_and_assert_failure "Resource disk partition $RESOURCE_DISK_PART1_RESOLVED is already mounted or in use"
}

test_resource_already_mounted_reformatted() {
    configure_scsi_resource_disk 1
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"
    mkfs.ext4 -q -F "$RESOURCE_DISK"
    partprobe_safe
    mount_safe "$RESOURCE_DISK" /media
    configure_nvme_disks 0

    run_and_assert_failure "Device /dev/disk/azure/resource is already mounted or in use"
}

test_resource_already_partitioned_multiple() {
    configure_scsi_resource_disk 1
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"

    parted -s "$RESOURCE_DISK" mklabel gpt mkpart primary ext4 0% 50%
    parted -s "$RESOURCE_DISK" mkpart primary ext4 50% 100%
    partprobe_safe
    configure_nvme_disks 0

    run_and_assert_failure "Device /dev/disk/azure/resource has 2 partition(s)"
}

test_resource_existing_partition_reformatted() {
    configure_scsi_resource_disk 1
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"

    mkfs.ext4 -q -F "${RESOURCE_DISK_PART1_RESOLVED}"
    partprobe_safe
    configure_nvme_disks 0

    run_and_assert_failure "Resource disk partition $RESOURCE_DISK_PART1_RESOLVED has type=ext4, expected type=ntfs"
}

test_resource_unformatted() {
    configure_scsi_resource_disk 1
    configure_conf "AZURE_EPHEMERAL_DISK_SETUP_SCSI_RESOURCE=true"

    reset_disk "$RESOURCE_DISK"
    partprobe_safe
    configure_nvme_disks 0

    run_and_assert_success "Mounted /dev/disk/azure/resource at /mnt with fs=ext4"
}

run_tests() {
    SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
    TESTS=$(grep -Eo '^test_[a-zA-Z0-9_]+\(\)' "$SCRIPT_PATH" | sed 's/()//' | paste -sd' ' -)
    START_INDEX=${START_INDEX:-0}
    START_COUNT=$((START_INDEX + 1))
    TEST_COUNT=0
    for TEST in $TESTS; do
        TEST_COUNT=$((TEST_COUNT + 1))
        if [ "$TEST_COUNT" -lt "$START_COUNT" ]; then
            echo "Skipping test #$TEST_COUNT: $TEST"
            continue
        fi
        reset_all
        echo "Running test #$TEST_COUNT: $TEST"
        $TEST
    done
}

run_tests
echo "All tests passed!"
