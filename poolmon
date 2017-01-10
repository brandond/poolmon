#!/usr/bin/perl
# vim: ai ts=4 sts=4 et sw=4
#
# Director mailserver pool monitoring script, meant to roughly duplicate the
# functionality of node health monitors on dedicated load-balancers like LVS or
# F5 BigIP LTM. This script can be safely run on more than one director host
# simultaneously, although differences in node reachability may result in
# mailserver vhost count flapping.
#
# Consult the help text for more details on functionality.
#
# Brandon Davidson <brad@oatmail.org>
#
### License:
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 2, or (at your option) any
# later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
###

use strict;
use Getopt::Long;
use IO::Socket::UNIX;
use IO::Socket::INET6;
use POSIX qw(setsid strftime);
use Sys::Syslog qw( :DEFAULT setlogsock);

$SIG{'PIPE'} = 'IGNORE';

my @PORTS;
my @SSL_PORTS;
my $DEBUG    = 0;
my $NOFORK   = 0;
my $TIMEOUT  = 5;
my $INTERVAL = 30;
my $PIDOPEN  = 0;
my $ORIGPID  = 0;
my $PIDFILE  = '/var/run/poolmon.pid';
my $LOGFILE  = '/var/log/poolmon.log';
my $DIRECTOR = '/var/run/dovecot/director-admin';
my $CREDFILE = '';
my $USERNAME = '';
my $PASSWORD = '';
my $LMTP_FROM = '';
my $LMTP_TO = '';

Getopt::Long::Configure("bundling");
GetOptions('p|port=s'     => \@PORTS,
           's|ssl=s'      => \@SSL_PORTS,
           'd|debug'      => \$DEBUG,
           't|timeout=i'  => \$TIMEOUT,
           'l|logfile=s'  => \$LOGFILE,
           'k|lockfile=s' => \$PIDFILE,
           'i|interval=i' => \$INTERVAL,
           'f|foreground' => \$NOFORK,
           'S|socket=s'   => \$DIRECTOR,
           'h|help|?'     => \&help,
           'c|credfile=s' => \&opt_credfile,
           'lmtp-from=s'  => \$LMTP_FROM,
           'lmtp-to=s'    => \$LMTP_TO,
    ) or help();

unless (@PORTS || @SSL_PORTS){
    @PORTS = qw(110 143);
}

if (@SSL_PORTS) {
    eval("use IO::Socket::SSL;");
    if ($@) {
        die "$@";
    }
}

check_pidfile();
unless($NOFORK){
    daemonize();
}

while(1){
    scan_host_loop();
    sleep($INTERVAL);
}
exit(0);

### It's subroutines, all the way down.

# Print help text and exit
sub help {
    print "Usage: $0 [<args>]
Retrieves a set of mailserver hosts from a Dovecot director and performs
parallel checks against a list of ports.

If any port on a host cannot be connected to or fails to present a banner line
within the timeout period, that host is disabled by setting its status to
'down', and flushing active mappings from that host. If a disabled host passes
all host checks, its status is restored to 'up'.

Arguments:
  -d, --debug           Show additional logging (default: false)
  -f, --foreground      Run in foreground (default: false)
  -h, --help            This text
  -i, --interval=SECS   Scan interval in seconds (default: 30)
  -k, --lockfile=PATH   PID/lockfile location (default: /var/run/poolmon.pid)
  -l, --logfile=PATH    Log file location (default: /var/log/poolmon.log)
                        Set to 'syslog' for writing to local syslog socket
  -p, --port=PORT       Port to check; repeat for multiple (default: 110, 143)
  -s  --ssl=PORT        Port with SSL/TLS; repeat for multiple (default: none)
                        If the port is recognized as common IMAP or POP3 port,
                        health checks will look for a valid connect banner.
                        You can force a protocol (IMAP or POP3) by specifying
                        it before the port, separated by a colon. Example:
                          --port POP3:110 --ssl IMAP:993
  -c  --credfile=PATH   File with credentials to authenticate as, mode 0600.
                          - Username on 1st line.
                          - Password on 2nd line.
                        (default: health checks will not attempt authentication)
  --lmtp-from=ADDR      Sender e-mail address for LMTP
  --lmtp-to=ADDR        Recipient e-mail address for LMTP
  -S, --socket=PATH     Path to Dovecot director-admin socket
                        (default: /var/run/dovecot/director-admin)
  -t, --timeout=SECS    Port health check timeout in seconds (default: 5)
";
    exit(1);
}

# Get list of mailservers from local director and scan them
sub scan_host_loop {
    # Get mailserver list
    my $sock = director_connect() || return;
    my @lines;
    my %CHILDREN;
    print $sock "HOST-LIST\n";
    while(my $line = readline($sock)){
        last if $line eq "\n";
        chomp $line;
        push(@lines, $line);
    }
    close($sock);
    undef($sock);
    $DEBUG && write_log('Director returned ',scalar(@lines),' hosts');

    # Start host scans
    foreach my $line (@lines){
        if(my ($host, $weight, $clients, $tag, $updown) = split("\t", $line)){
            my $pid = fork();
            if ($pid == 0) {
                exit(scan_host($host, $updown));
            } elsif ($pid > 0) {
                $CHILDREN{$pid} = [$host, $updown];
            } else {
                write_err("Failed to fork scan process for host $host: $!");
            }
        }
    }

    # Take action based on check results returned by subprocesses
    while(my $pid = wait()){
        my $OK = $? >> 8;
        last if $pid == -1;
        my ($host, $updown) = @{$CHILDREN{$pid}};
        $DEBUG && write_log("Scan of host $host with status $updown by PID $pid exited with status $OK");
        if ($OK) { # Enable host if currently disabled (updown=D)
            enable_host($host) if $updown eq "D";
        } else {  # Disable host if currently enabled (updown=U)
            disable_host($host) if $updown eq "U";
        }
        undef($CHILDREN{$pid});
    }
    $DEBUG && write_log('Host scans complete');
}

# Connect to local director and perform version handshake
sub director_connect {
    my $HANDSHAKE = "VERSION\tdirector-doveadm\t1\t0\n";
    my $sock = new IO::Socket::UNIX($DIRECTOR);
    if ($sock) {
        print $sock $HANDSHAKE;
        unless (readline($sock) eq $HANDSHAKE){
            write_err("Director handshake failed!");
            close($sock);
        }
    } else {
        write_err("Failed to connect to director: $!");
    }
    return $sock;
}

# Scan all ports on a given host. 1 == success. 0 == failure
sub scan_host {
    my ($host, $updown) = @_;
    my $OK = 1;
    # Check non-SSL ports first
    foreach my $port (@PORTS){
        if (! scan_port($host, $port, 0)){
            sleep(3);
            for (my $i=0; $i <= 3; $i++) {
                if (! scan_port($host, $port, 0)){
                    $OK = 0;
                    last;
                }
                sleep(0.5);
           }
        }
    }
    # Skip SSL checks if standard checks indicated failure
    return 0 unless $OK;
    foreach my $port (@SSL_PORTS){
        if (! scan_port($host, $port, 1)){
            sleep(3);
            for (my $i=0; $i <= 3; $i++) {
                if (! scan_port($host, $port, 1)){
                    $OK = 0;
                    last;
                }
                sleep(0.5);
           }
        }
    }
    return $OK;
}

# Check a port on a host, with optional SSL and login
sub scan_port {
    no strict 'subs';
    my $host = shift || return;
    my $port = shift || return;
    my $ssl  = shift;
    my $sock = $ssl ? IO::Socket::SSL : IO::Socket::INET6;
    my $prot;
    my $ret;

    ($port, $prot) = get_port_proto($port);
    $sock = $sock->new(PeerAddr => $host,
                       PeerPort => $port,
                       Timeout  => $TIMEOUT);

    $ret = eval {
        local $SIG{ALRM} = sub { 
            $DEBUG && write_log("Timeout");
            die "Timeout\n"; 
        };
        alarm $TIMEOUT;
        if ($sock){
            if ($prot eq 'IMAP'){
                return scan_imap($host, $port, $sock);
            } elsif ($prot eq 'POP3'){
                return scan_pop3($host, $port, $sock);
            } elsif ($prot eq 'LMTP'){
                return scan_lmtp($host, $port, $sock);
            } elsif (readline($sock)){
                $DEBUG && write_log("$host:$port Connection OK");
                return 1
            }
        } else {
            $DEBUG && write_log("$host:$port Connection Failed");
            return 0;
        }
        alarm 0;
    };

    if ($@){
        $DEBUG && write_log("$host:$port Read Timeout");
    }

    return $ret;
}

sub scan_imap {
    my $host = shift || return;
    my $port = shift || return;
    my $sock = shift || return;
    my $line = readline($sock);
    if ($line =~ m/LOGINDISABLED/){
        write_err("$host:$port IMAP Server Reports Plaintext Login Disabled - check login_trusted_networks");
        return 1;
    } elsif ($line =~ m/^\* OK/){
        if ($USERNAME && $PASSWORD){
            printf $sock "01 LOGIN %s {%d}\r\n%s\r\n", $USERNAME, length($PASSWORD), $PASSWORD;
            my $literal = readline($sock);
            my $logstat = readline($sock);
            if ($literal =~ m/^\+ OK/ && $logstat =~ m/^01 OK/){
                $DEBUG && write_log("$host:$port IMAP Login OK");
                return 1;
            } else {
                $DEBUG && write_log("$host:$port IMAP Login Failed");
                $DEBUG && write_log("\t\t$logstat");
                return 0;
            }
        } else {
            printf $sock "01 LOGOUT\r\n";
            $DEBUG && write_log("$host:$port IMAP Banner OK");
            return 1;
        }
    } else {
        $DEBUG && write_log("$host:$port IMAP Banner Check Failed");
        return 0;
    }
}

sub scan_pop3 {
    my $host = shift || return;
    my $port = shift || return;
    my $sock = shift || return;
    my $line = readline($sock);
    if ($line =~ m/\+OK/){
        if ($USERNAME && $PASSWORD){
            printf $sock "USER %s\r\nPASS %s\r\n", $USERNAME, $PASSWORD;
            my $userval = readline($sock);
            my $logstat = readline($sock);
            if ($userval =~ m/^-ERR Plaintext authentication disallowed/){
                write_err("$host:$port POP3 Server Reports Plaintext Login Disabled - check login_trusted_networks");
                return 1;
            } elsif ($userval =~ m/^\+OK/ && $logstat =~ m/^\+OK/){
                $DEBUG && write_log("$host:$port POP3 Login OK");
                return 1;
            } else {
                $DEBUG && write_log("$host:$port POP3 Login Failed");
                $DEBUG && write_log("\t\t$logstat");
                return 0;
        }
        } else {
            $DEBUG && write_log("$host:$port POP3 Banner OK");
            return 1;
        }
    } else {
        $DEBUG && write_log("$host:$port POP3 Banner Check Failed");
        return 0;
    }
}

sub scan_lmtp {
    my $host = shift || return;
    my $port = shift || return;
    my $sock = shift || return;
    my $line = readline($sock);
    if ($line =~ m/^2\d\d /){
        if ($LMTP_TO){
            printf $sock "MAIL FROM:<%s>\r\n", $LMTP_FROM;
            my $mailreply = readline($sock);
            if ($mailreply !~ m/^2\d\d /){
                write_err("$host:$port LMTP Server Rejects sender address");
                return 0;
            }

            printf $sock "RCPT TO:<%s>\r\n", $LMTP_TO;
            my $mailreply = readline($sock);
            if ($mailreply !~ m/^2\d\d /){
                write_err("$host:$port LMTP Server Rejects recipient address");
                return 0;
            }

            $DEBUG && write_log("$host:$port LMTP OK");
            return 1;
        } else {
            $DEBUG && write_log("$host:$port LMTP Banner OK");
            return 1;
        }
    } else {
        $DEBUG && write_log("$host:$port LMTP Banner Check Failed");
        return 0;
    }
}

# Extract port and protocol from combined port command-line option
sub get_port_proto {
    my $port = shift;

    if ($port == 143 || $port == 993 || $port =~ m/IMAP:(\d+)/i){
        $port = $1 ? $1 : $port;
        return $port, 'IMAP';
    } elsif ($port == 110 || $port == 995 || $port =~ m/POP3:(\d+)/i){
        $port = $1 ? $1 : $port;
        return $port, 'POP3';
    } elsif ($port == 24 || $port =~ m/LMTP:(\d+)/i){
        $port = $1 ? $1 : $port;
        return $port, 'LMTP';
    } else {
        return $port, 'UNKNOWN';
    }
}

# Mark host down and flush associations
# Note that there's no way to kill active sessions, they'll have to time out
# on their own.
sub disable_host {
    my $host = shift || return;
    my $sock = director_connect() || return;
    print $sock "HOST-DOWN\t$host\n";
    print $sock "HOST-FLUSH\t$host\n";
    close($sock);
    undef($sock);
    write_log("$host disabled");
}

# Mark host as up
sub enable_host {
    my $host = shift || return;
    my $sock = director_connect() || return;
    print $sock "HOST-UP\t$host\n";
    close($sock);
    undef($sock);
    write_log("$host enabled");
}

# Append a line to stdout
sub write_log {
    if ($LOGFILE eq "syslog") {
        write_to_syslog("info", join('', @_));
    } else {
        printf(STDOUT "%s LOG %s\n", strftime("%h %d %H:%M:%S", localtime()), join('', @_));
    }
}

# Append a line to stderr
sub write_err {
    if ($LOGFILE eq "syslog") {
        write_to_syslog("err", join('', @_));
    } else {
        printf(STDERR "%s ERR %s\n", strftime("%h %d %H:%M:%S", localtime()), join('', @_));
    }
}

sub write_to_syslog {
    my ($priority, $msg) = @_;
    return 0 unless ($priority =~ /info|err|debug/);

    setlogsock("unix");
    openlog("poolmon", "pid,cons", "user");
    syslog($priority, $msg);
    closelog();
    return 1;
}

# Check to see if the pidfile exists and the indicated pid is still running
sub check_pidfile {
    if (-e $PIDFILE){
        my $FH;
        open($FH, "<$PIDFILE");
        my $oldpid = readline($FH);
        close($FH);
        chomp $oldpid;
        if (kill(0, $oldpid)){
            write_err("Already running as pid $oldpid");
            exit(1);
        }
    }
}

# Remove the pidfile and exit
sub remove_pidfile {
    return unless $PIDOPEN;
    if ($$ == $ORIGPID) {
        write_log('Shutting down');
        unlink($PIDFILE);
    }
}

sub opt_credfile {
    my ($opt, $value)= @_;
    if ( -e $value ){
        $CREDFILE = $value;
        load_credentials();
    } else {
        write_err("Credential file '$value' not found!");
        exit(1);
    }
}

sub load_credentials {
    return unless $CREDFILE;
    # Check permissions on credentials file
    if ((stat($CREDFILE))[2] & 077){
        write_err("You should really chmod 600 $CREDFILE");
    }
    if(open(my $credfh, "<$CREDFILE")){
        $USERNAME = readline($credfh);
        $PASSWORD = readline($credfh);
        close($credfh);
        chomp($USERNAME);
        chomp($PASSWORD);
        if ($USERNAME && $PASSWORD){
            $DEBUG && write_log("Loaded credentials from $CREDFILE");
        } else {
            write_err("Could not read username and password from $CREDFILE");
        }
    } else {
        write_err("Could not open credential file: $!");
    }
}



# Fork into background and write pidfile
sub daemonize {
    my $FH;

    # Open pidfile and register cleanup handlers
    # Do this before forking so we can abort on failure
    $PIDOPEN = open($FH, ">$PIDFILE") or die "Can't open pidfile $PIDFILE: $!";
    $SIG{'INT'} = sub {
        $DEBUG && write_log("Caught signal INT");
        remove_pidfile();
    };
    $SIG{'QUIT'} = sub {
        $DEBUG && write_log("Caught signal QUIT");
        remove_pidfile();
    };
    $SIG{'TERM'} = sub {
        $DEBUG && write_log("Caught signal TERM");
        remove_pidfile();
    };

    # Disconnect from terminal and session
    chdir('/')         or die "Can't chdir to /: $!";
    umask(0);
    open(STDIN, '</dev/null')  or die "Can't read /dev/null: $!";
    if ($LOGFILE ne "syslog") {
        open(STDOUT, ">>$LOGFILE") or die "Can't write to $LOGFILE: $!";
        open(STDERR, ">>$LOGFILE") or die "Can't write to $LOGFILE: $!";
    }
    defined(my $pid = fork())  or die "Can't fork: $!";
    $pid && exit(0);
    setsid()           or die "Can't start a new session: $!";

    # Write forked PID to pidfile and startup message to log
    write_log("Forked to background as PID $$");
    print $FH "$$\n";
    close($FH);
    $ORIGPID = $$;

    # Reopen logfiles on HUP
    $SIG{'HUP'} = sub {
        if ($LOGFILE ne "syslog") {
          open(STDOUT, ">>$LOGFILE") or die "Can't reopen $LOGFILE: $!";
          open(STDERR, ">>$LOGFILE") or die "Can't reopen $LOGFILE: $!";
        }
        write_log("Logfile reopened");
        load_credentials();
    }
}

# Ensure pidfile cleanup on exit
END {
    remove_pidfile();
}
