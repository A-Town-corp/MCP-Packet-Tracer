"""IOS CLI generator for device management (security and management plane)."""
from __future__ import annotations


def generate_device_security_cli(
    hostname: str | None = None,
    enable_secret: str | None = None,
    console_password: str | None = None,
    vty_password: str | None = None,
    ssh: dict | None = None,
    banner_motd: str | None = None,
    service_password_encryption: bool = False,
    domain_name: str | None = None,
) -> list[str]:
    """Generate IOS body lines to configure device security settings.

    Emits (in order) only the sections that are actually requested:
      - hostname
      - enable secret
      - service password-encryption
      - ip domain-name  (global, only when ssh is NOT provided)
      - banner motd
      - line console 0 block  (when console_password given)
      - SSH block  (when ssh dict given; its vty block replaces the plain vty block)
      - line vty 0 15 block  (plain password, only when ssh is NOT given)

    Args:
        hostname: Router/switch hostname.
        enable_secret: Privileged-exec secret.
        console_password: Console line password (triggers `login`).
        vty_password: VTY password (used only when ssh is not provided).
        ssh: Dict with keys "domain" (str), "username" (str), "password" (str),
             and optionally "version" (int, default 2) and "modulus" (int, default 1024).
        banner_motd: Text placed between `#` delimiters on a single banner line.
        service_password_encryption: If True, emit `service password-encryption`.
        domain_name: Global domain name; ignored when ssh is provided (the ssh
                     block supplies its own `ip domain-name`).

    Returns:
        A list of IOS body lines (no `enable`, `configure terminal`, `end`, or
        `write memory`).

    Raises:
        ValueError: If no argument is supplied (nothing to configure).
        ValueError: If ssh is provided but is missing "domain", "username",
                    or "password" keys.
    """
    _any = (
        hostname is not None
        or enable_secret is not None
        or console_password is not None
        or vty_password is not None
        or ssh is not None
        or banner_motd is not None
        or service_password_encryption
        or domain_name is not None
    )
    if not _any:
        raise ValueError("nothing to configure")

    if ssh is not None:
        missing = [k for k in ("domain", "username", "password") if k not in ssh]
        if missing:
            raise ValueError(
                f"ssh dict is missing required key(s): {', '.join(missing)}"
            )

    lines: list[str] = []

    # Global: hostname
    if hostname is not None:
        lines.append(f"hostname {hostname}")

    # Global: enable secret
    if enable_secret is not None:
        lines.append(f"enable secret {enable_secret}")

    # Global: service password-encryption
    if service_password_encryption:
        lines.append("service password-encryption")

    # Global: ip domain-name (standalone, only when ssh is NOT given)
    if domain_name is not None and ssh is None:
        lines.append(f"ip domain-name {domain_name}")

    # Global: banner motd
    if banner_motd is not None:
        lines.append(f"banner motd #{banner_motd}#")

    # Console block
    if console_password is not None:
        lines.append("line console 0")
        lines.append(f" password {console_password}")
        lines.append(" login")
        lines.append(" exit")

    # SSH block (also owns its own vty block)
    if ssh is not None:
        version = int(ssh.get("version", 2))
        modulus = int(ssh.get("modulus", 1024))
        lines.append(f"ip domain-name {ssh['domain']}")
        lines.append(f"username {ssh['username']} password {ssh['password']}")
        lines.append(
            f"crypto key generate rsa general-keys modulus {modulus}"
        )
        lines.append(f"ip ssh version {version}")
        # VTY block with SSH transport
        lines.append("line vty 0 15")
        lines.append(" transport input ssh")
        lines.append(" login local")
        lines.append(" exit")
    elif vty_password is not None:
        # Plain VTY block (no SSH)
        lines.append("line vty 0 15")
        lines.append(f" password {vty_password}")
        lines.append(" login")
        lines.append(" exit")

    return lines


def generate_management_cli(
    ntp_servers: list[str] | None = None,
    snmp: dict | None = None,
    logging_hosts: list[str] | None = None,
    clock_timezone: dict | None = None,
) -> list[str]:
    """Generate IOS body lines for management-plane services.

    All commands are global (no leading space).

    Args:
        ntp_servers: List of NTP server IP addresses.
        snmp: Dict with keys "community" (str), "access" (str "ro"|"rw",
              default "ro"), and optionally "location" (str) and "contact" (str).
        logging_hosts: List of syslog server IP addresses.
        clock_timezone: Dict with keys "name" (str) and "offset" (int).

    Returns:
        A list of IOS body lines (no `enable`, `configure terminal`, `end`, or
        `write memory`).

    Raises:
        ValueError: If no argument is supplied (nothing to configure).
    """
    if not any([ntp_servers, snmp, logging_hosts, clock_timezone]):
        raise ValueError("nothing to configure")

    lines: list[str] = []

    # NTP servers
    if ntp_servers:
        for ip in ntp_servers:
            lines.append(f"ntp server {ip}")

    # SNMP community and optional location / contact
    if snmp is not None:
        community = snmp.get("community")
        if not community:
            raise ValueError("snmp requires a non-empty 'community'")
        access = str(snmp.get("access") or "ro").upper()
        if access not in ("RO", "RW"):
            raise ValueError(f"snmp 'access' must be 'ro' or 'rw', got {snmp.get('access')!r}")
        lines.append(f"snmp-server community {community} {access}")
        if snmp.get("location"):
            lines.append(f"snmp-server location {snmp['location']}")
        if snmp.get("contact"):
            lines.append(f"snmp-server contact {snmp['contact']}")

    # Logging hosts
    if logging_hosts:
        for ip in logging_hosts:
            lines.append(f"logging host {ip}")

    # Clock timezone
    if clock_timezone is not None:
        name = clock_timezone["name"]
        offset = int(clock_timezone["offset"])
        lines.append(f"clock timezone {name} {offset}")

    return lines
