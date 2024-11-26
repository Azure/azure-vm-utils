#!/bin/bash
# shellcheck disable=SC1091
set -eu -o pipefail

source /etc/os-release

distro="$ID"
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
version="$(git describe --tags | cut -f 1 -d "-" | sed 's/^v//')"
release="dev_$(git describe --tags --dirty --always | sed 's/^v//g' | sed 's/-/_/g')"
output_dir="${project_dir}/out"

echo "project root: ${project_dir}"
echo "build version: ${version}"
echo "build release: ${release}"

set -x

# Create rpmbuild directory layout.
build_dir="$(mktemp -d)"
mkdir -p "${build_dir}"/{BUILD,RPMS,SOURCES,SPECS,SRPMS}

# Create source tarball.
output_source="${build_dir}/SOURCES/azure-vm-utils_dev.tgz"
cd "$project_dir"
git archive --verbose --format=tar.gz --prefix="azure-vm-utils-${version}/" HEAD --output "${output_source}"

# Create spec file from template.
cd "${project_dir}/packaging/${distro}"

# Install dependencies.
build_requirements=$(grep ^BuildRequires azure-vm-utils.spec | awk '{{print $2}}' | tr '\n' ' ')
sudo dnf install -y ${build_requirements}

# Build RPM.
rpmbuild -ba --define "__git_version ${version}" --define "__git_release ${release}" --define "_topdir ${build_dir}" azure-vm-utils.spec

# Copy RPM to output directory.
mkdir -p "${output_dir}"
rm -f "${output_dir}"/*.rpm
cp -v "${build_dir}"/RPMS/*/"azure-vm-utils-${version}-${release}".*.rpm "${output_dir}"
