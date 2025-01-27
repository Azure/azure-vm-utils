Name:           azure-vm-utils
Version:        %{__git_version}
Release:        %{__git_release}%{?dist}
Summary:        Utilities and udev rules for Linux on Azure

License:        MIT
URL:            https://github.com/Azure/%{name}
Source0:        %{name}_dev.tgz

BuildRequires:  cmake
BuildRequires:  gcc

%description
A collection of utilities and udev rules to make the most of the Linux
experience on Azure.

%prep
%autosetup

%build
%cmake -DVERSION="%{version}-%{release}" -DENABLE_TESTS=1
%cmake_build

%install
%cmake_install

%check
%ctest

%files
%{_exec_prefix}/lib/dracut/modules.d/97azure-disk/module-setup.sh
%{_exec_prefix}/lib/udev/rules.d/80-azure-disk.rules
%{_sbindir}/azure-nvme-id
%{_mandir}/man8/azure-nvme-id.8.gz

%changelog
%autochangelog
