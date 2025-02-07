Name:           azure-vm-utils
Version:        %{__git_version}
Release:        %{__git_release}%{?dist}
Summary:        Utilities and udev rules for Linux on Azure

License:        MIT
URL:            https://github.com/Azure/%{name}
Source0:        azure-vm-utils_dev.tgz

BuildRequires:  binutils
BuildRequires:  cmake
BuildRequires:  gcc
BuildRequires:  glibc-devel
BuildRequires:  json-c-devel
BuildRequires:  kernel-headers
BuildRequires:  libcmocka-devel
BuildRequires:  make

%description
A collection of utilities and udev rules to make the most of the Linux
experience on Azure.

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
%{_libdir}/dracut/modules.d/97azure-disk/module-setup.sh
%{_libdir}/udev/rules.d/80-azure-disk.rules
%{_sbindir}/azure-nvme-id
%{_mandir}/man8/azure-nvme-id.8.gz
