Name:           azure-vm-utils
Version:        %{__git_version}
Release:        %{__git_release}%{?dist}
Summary:        Utilities and udev rules for Linux on Azure

License:        MIT
URL:            https://github.com/Azure/%{name}
Source0:        %{name}_dev.tgz

BuildRequires:  cmake
BuildRequires:  gcc
BuildRequires:  json-c-devel
BuildRequires:  libcmocka-devel
Requires:       mdadm
Requires:       util-linux

%description
A collection of utilities and udev rules to make the most of the Linux
experience on Azure.

%package selftest
Summary:        Self-test script for Azure VM Utils
Requires:       %{name} = %{version}-%{release}
%if 0%{?rhel} == 8 || 0%{?centos} == 8 || 0%{?almalinux} == 8
Requires:       python39
%else
Requires:       python3 >= 3.9
%endif

%description selftest
This package contains the self-test script for the Azure VM Utils package.

%prep
%autosetup

%build
%cmake -DVERSION="%{version}-%{release}" -DAZURE_NVME_ID_INSTALL_DIR="%{_bindir}"
%cmake_build

%install
%cmake_install

%check
%ctest

%if 0%{?rhel} == 8 && 0%{?centos} == 8 && 0%{?almalinux} == 8
%undefine __brp_mangle_shebangs
%endif

%files
%{_exec_prefix}/lib/dracut/modules.d/97azure-disk/module-setup.sh
%{_exec_prefix}/lib/dracut/modules.d/97azure-unmanaged-sriov/module-setup.sh
%{_exec_prefix}/lib/systemd/network/01-azure-unmanaged-sriov.network
%{_exec_prefix}/lib/systemd/system/azure-ephemeral-disk-setup.service
%{_exec_prefix}/lib/udev/rules.d/10-azure-unmanaged-sriov.rules
%{_exec_prefix}/lib/udev/rules.d/80-azure-disk.rules
%{_bindir}/azure-ephemeral-disk-setup
%{_bindir}/azure-nvme-id
%{_mandir}/man8/azure-ephemeral-disk-setup.8.gz
%{_mandir}/man8/azure-nvme-id.8.gz
%{_sysconfdir}/azure-ephemeral-disk-setup.conf

%files selftest
%{_bindir}/azure-vm-utils-selftest
%{_mandir}/man8/azure-vm-utils-selftest.8.gz

%changelog
* Wed Feb 05 2025 Test <test.packaging@no.where> - %{__git_version}-%{__git_release}
- Test test test
