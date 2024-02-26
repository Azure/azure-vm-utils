%global version %(git describe --tags --abbrev=0 | sed 's/^v//')
%global release %(git describe --tags --dirty | sed 's/^[^-]*-//' | sed 's/-/_/g')
%global sourcedir %(pwd)

Name:           azure-nvme-utils
Version:        %{version}
Release:        %{release}%{?dist}
Summary:        Utility and udev rules to help identify Azure NVMe devices

License:        MIT
URL:            https://github.com/Azure/%{name}
Source0:        %{name}-dev.tar.gz

BuildRequires:  binutils
BuildRequires:  cmake
BuildRequires:  gcc
BuildRequires:  glibc-devel
BuildRequires:  kernel-headers

%description
Utility and udev rules to help identify Azure NVMe devices.

%prep
git archive --format=tar.gz --prefix=%{name}-%{version}/ HEAD --output %{_topdir}/SOURCES/%{name}-dev.tar.gz --remote %{sourcedir}/.git
%autosetup

%build
%cmake .
make %{?_smp_mflags}

%install
make install DESTDIR=%{buildroot}

%files
/usr/sbin/azure-nvme-id
/lib/udev/rules.d/80-azure-nvme.rules
