Name: poolmon
Version:  0.1.1
Release:  1%{?dist}
Summary: poolmon is a director mailserver pool monitoring script for Dovecot

Group: Applications/Publishing
License: GPLv2+        
URL: http://github.com/brandond/poolmon
Source0: http://github.com/brandond/%{name}/raw/%{version}/poolmon
Source1: http://github.com/brandond/%{name}/raw/%{version}/redhat/poolmon.init
Source2: http://github.com/brandond/%{name}/raw/%{version}/redhat/poolmon.sysconfig

BuildArch: noarch
BuildRoot: %{_tmppath}/%{name}-%{version}-%{release}-root-%(%{__id_u} -n)
Requires: dovecot

%description
Poolmon is a director mailserver pool monitoring script for Dovecot, meant to
roughly duplicate the functionality of node health monitors on dedicated load-
balancers like Linux LVS or F5 BigIP hardware.

%prep

%build

%install
rm -rf %{buildroot}

chmod a+x %{SOURCE0} %{SOURCE1}

mkdir -p %{buildroot}%{_sbindir}
mkdir -p %{buildroot}%{_sysconfdir}/rc.d/init.d/
mkdir -p %{buildroot}%{_sysconfdir}/sysconfig/

cp %{SOURCE0} %{buildroot}%{_sbindir}
cp %{SOURCE1} %{buildroot}%{_sysconfdir}/rc.d/init.d/%{name}
cp %{SOURCE2} %{buildroot}%{_sysconfdir}/sysconfig/%{name}

%clean
rm -rf %{buildroot}

%files
%defattr(-,root,root,-)
%{_sbindir}/%{name}
%{_sysconfdir}/rc.d/init.d/%{name}
%config %{_sysconfdir}/sysconfig/%{name}

%changelog
* Thu Aug 19 2010 Brandon Davidson <brandond@uoregon.edu>
- Initial Package 

