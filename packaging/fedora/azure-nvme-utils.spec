Name:           azure-nvme-utils
Version:        %{__git_version}
Release:        %{__git_release}%{?dist}
Summary:        Utility and udev rules to help identify Azure NVMe devices

License:        MIT
URL:            https://github.com/Azure/%{name}
Source0:        %{name}_dev.tgz

BuildRequires:  cmake
BuildRequires:  gcc

%description
Utility and udev rules to help identify Azure NVMe devices.

%prep
%autosetup

%build
%cmake -DVERSION="%{version}-%{release}"
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
