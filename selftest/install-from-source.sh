#!/bin/sh

# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

set -eu

source_dir=$1
version=$2
trap 'rm -rf "$source_dir"' EXIT

configure_selftest_python()
{
    # SLES 15 keeps Python 3.6 as python3 and provides python3.11 alongside it.
    for interpreter in python3 python3.11; do
        if command -v "$interpreter" >/dev/null 2>&1 &&
            "$interpreter" -c 'from dataclasses import dataclass; from typing import Literal' 2>/dev/null; then
            interpreter_path=$(command -v "$interpreter")
            sed -i "1c\\#!$interpreter_path" "$1"
            printf 'Selftest Python: %s\n' "$interpreter_path"
            return
        fi
    done
    echo "Selftest requires Python 3.8 or newer with dataclasses and typing.Literal" >&2
    return 1
}

if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    export NEEDRESTART_MODE=a
    set -- -o Acquire::Retries=2 -o DPkg::Lock::Timeout=-1
    apt-get "$@" -o APT::Update::Error-Mode=any update
    apt-get "$@" install -y --no-install-recommends \
        gcc libc6-dev make cmake pkg-config libjson-c-dev
elif command -v zypper >/dev/null 2>&1; then
    zypper --non-interactive refresh
    zypper --non-interactive install --no-recommends \
        gcc glibc-devel make cmake pkg-config libjson-c-devel
elif command -v dnf >/dev/null 2>&1; then
    dnf -y --setopt=install_weak_deps=False install \
        gcc glibc-devel make cmake pkgconf-pkg-config json-c-devel
elif command -v tdnf >/dev/null 2>&1; then
    tdnf -y install gcc glibc-devel make cmake pkg-config json-c-devel
else
    echo "Unsupported guest: source-install mode requires apt-get, zypper, dnf or tdnf" >&2
    exit 1
fi

cmake -S "$source_dir" -B "$source_dir/build" \
    -DENABLE_TESTS=OFF -DCMAKE_BUILD_TYPE=Debug \
    -DCMAKE_INSTALL_PREFIX=/usr -DVERSION="$version"
cmake --build "$source_dir/build" --parallel 2
cmake --install "$source_dir/build"
configure_selftest_python /usr/sbin/azure-vm-utils-selftest
systemctl daemon-reload

# Include the new rules and helpers in early boot as well as the root filesystem.
if command -v update-initramfs >/dev/null 2>&1; then
    update-initramfs -u -k all
elif command -v dracut >/dev/null 2>&1; then
    dracut --regenerate-all --force
else
    echo "Cannot update initramfs: neither update-initramfs nor dracut is available" >&2
    exit 1
fi

while IFS= read -r installed; do
    sha256sum "$installed"
done < "$source_dir/build/install_manifest.txt" > /var/tmp/azure-vm-utils-selftest.sha256
sha256sum --check /var/tmp/azure-vm-utils-selftest.sha256
/usr/sbin/azure-nvme-id --version
