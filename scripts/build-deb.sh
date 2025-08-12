#!/bin/bash

set -eux -o pipefail

if [[ $UID -ne 0 ]]; then
    sudo_cmd="sudo"
else
    sudo_cmd=""
fi

# Ensure dependencies are installed and up-to-date.
$sudo_cmd apt update
$sudo_cmd apt install -y \
        build-essential \
        clang-format \
        cmake \
        cppcheck \
        devscripts \
        debhelper \
        gcc \
        initramfs-tools \
        libcmocka-dev \
        libjson-c-dev \
        mdadm \
        pandoc \
        pkg-config \
        rsync

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
git_version="$(git describe --tags --always --dirty)"
git_ref="$(echo "${git_version}" | sed 's/.*-g//' | sed 's/-dirty/DIRTY/')"
deb_version="$(echo "${git_version}" | sed 's/^v//' | sed 's/-.*//')+git${git_ref}"
output_dir="${project_dir}/out"

echo "project root: $project_dir"
echo "project version: $git_version"

cd "$project_dir"
mkdir -p debian
rsync -a packaging/debian/. debian/.

rm -f debian/changelog
if [[ -z ${DEBEMAIL:-} ]]; then
    git_user="$(git config user.name || echo Azure VM Utils CI)"
    git_email="$(git config user.email || echo azure/azure-vm-utils@github.com)"
    export DEBEMAIL="${git_user} <${git_email}>"
fi
dch --create -v "${deb_version}" --package "azure-vm-utils" "development build: ${git_version}"

debuild --no-tgz-check

mkdir -p "${output_dir}"
rm -f "${output_dir}"/*.deb
mv ../azure-vm-utils*"${deb_version}"* "${output_dir}"/
