"""Unit tests for the device management CLI generators."""

import pytest

from packet_tracer_mcp.infrastructure.generator.device_mgmt_cli_generator import (
    generate_device_security_cli,
    generate_management_cli,
)


# ---------------------------------------------------------------------------
# generate_device_security_cli
# ---------------------------------------------------------------------------

class TestGenerateDeviceSecurityCli:

    def test_hostname_only(self):
        lines = generate_device_security_cli(hostname="R1")
        assert "hostname R1" in lines
        assert len(lines) == 1

    def test_enable_secret(self):
        lines = generate_device_security_cli(enable_secret="cisco123")
        assert "enable secret cisco123" in lines

    def test_service_password_encryption(self):
        lines = generate_device_security_cli(service_password_encryption=True)
        assert "service password-encryption" in lines

    def test_domain_name_without_ssh(self):
        lines = generate_device_security_cli(domain_name="example.com")
        assert "ip domain-name example.com" in lines

    def test_domain_name_ignored_when_ssh_given(self):
        lines = generate_device_security_cli(
            domain_name="ignored.example.com",
            ssh={"domain": "real.example.com", "username": "admin", "password": "pass"},
        )
        assert "ip domain-name ignored.example.com" not in lines
        assert "ip domain-name real.example.com" in lines

    def test_banner_motd(self):
        lines = generate_device_security_cli(banner_motd="Authorized use only")
        assert "banner motd #Authorized use only#" in lines

    def test_console_block(self):
        lines = generate_device_security_cli(console_password="consolepass")
        assert "line console 0" in lines
        assert " password consolepass" in lines
        assert " login" in lines
        assert " exit" in lines

    def test_console_block_subcommand_indentation(self):
        lines = generate_device_security_cli(console_password="pass")
        idx = lines.index("line console 0")
        for sub in lines[idx + 1:]:
            if sub == " exit":
                break
            assert sub.startswith(" "), f"Expected leading space: {sub!r}"
            assert not sub.startswith("  "), f"Double-space: {sub!r}"

    def test_vty_plain_password(self):
        lines = generate_device_security_cli(vty_password="vtypass")
        assert "line vty 0 15" in lines
        assert " password vtypass" in lines
        assert " login" in lines

    def test_vty_not_emitted_when_ssh_given(self):
        lines = generate_device_security_cli(
            ssh={"domain": "lab.local", "username": "admin", "password": "cisco"}
        )
        assert " password" not in [l for l in lines if "vty" in l or l.startswith(" password")]
        # plain vty password line must be absent
        assert all(" password" not in l for l in lines if "line vty" not in l and l.startswith(" p"))

    def test_ssh_block_full(self):
        lines = generate_device_security_cli(
            ssh={
                "domain": "lab.local",
                "username": "admin",
                "password": "cisco123",
                "version": 2,
                "modulus": 1024,
            }
        )
        assert "ip domain-name lab.local" in lines
        assert "username admin password cisco123" in lines
        assert "crypto key generate rsa general-keys modulus 1024" in lines
        assert "ip ssh version 2" in lines
        assert "line vty 0 15" in lines
        assert " transport input ssh" in lines
        assert " login local" in lines
        assert " exit" in lines

    def test_ssh_default_version_and_modulus(self):
        lines = generate_device_security_cli(
            ssh={"domain": "lab.local", "username": "u", "password": "p"}
        )
        assert "crypto key generate rsa general-keys modulus 1024" in lines
        assert "ip ssh version 2" in lines

    def test_ssh_custom_modulus_and_version(self):
        lines = generate_device_security_cli(
            ssh={"domain": "lab.local", "username": "u", "password": "p",
                 "version": 1, "modulus": 2048}
        )
        assert "crypto key generate rsa general-keys modulus 2048" in lines
        assert "ip ssh version 1" in lines

    def test_full_security_config_order(self):
        """Verify the documented emission order for all sections."""
        lines = generate_device_security_cli(
            hostname="R1",
            enable_secret="cisco123",
            service_password_encryption=True,
            banner_motd="WARNING",
            console_password="con",
            ssh={"domain": "lab.local", "username": "admin", "password": "ssh123"},
        )
        hostname_idx = lines.index("hostname R1")
        secret_idx = lines.index("enable secret cisco123")
        spe_idx = lines.index("service password-encryption")
        banner_idx = lines.index("banner motd #WARNING#")
        console_idx = lines.index("line console 0")
        domain_idx = lines.index("ip domain-name lab.local")
        vty_idx = lines.index("line vty 0 15")

        assert hostname_idx < secret_idx < spe_idx < banner_idx
        assert banner_idx < console_idx
        assert console_idx < domain_idx < vty_idx

    def test_no_global_commands_have_leading_space(self):
        lines = generate_device_security_cli(
            hostname="R2",
            enable_secret="sec",
            service_password_encryption=True,
            domain_name="test.net",
            banner_motd="Hello",
        )
        global_cmds = [
            "hostname R2",
            "enable secret sec",
            "service password-encryption",
            "ip domain-name test.net",
            "banner motd #Hello#",
        ]
        for cmd in global_cmds:
            assert cmd in lines
            assert not cmd.startswith(" ")

    def test_error_on_empty_call(self):
        with pytest.raises(ValueError, match="nothing to configure"):
            generate_device_security_cli()

    def test_error_ssh_missing_domain(self):
        with pytest.raises(ValueError):
            generate_device_security_cli(
                ssh={"username": "admin", "password": "pass"}
            )

    def test_error_ssh_missing_username(self):
        with pytest.raises(ValueError):
            generate_device_security_cli(
                ssh={"domain": "lab.local", "password": "pass"}
            )

    def test_error_ssh_missing_password(self):
        with pytest.raises(ValueError):
            generate_device_security_cli(
                ssh={"domain": "lab.local", "username": "admin"}
            )


# ---------------------------------------------------------------------------
# generate_management_cli
# ---------------------------------------------------------------------------

class TestGenerateManagementCli:

    def test_ntp_single_server(self):
        lines = generate_management_cli(ntp_servers=["10.0.0.1"])
        assert "ntp server 10.0.0.1" in lines

    def test_ntp_multiple_servers(self):
        lines = generate_management_cli(ntp_servers=["10.0.0.1", "10.0.0.2"])
        assert "ntp server 10.0.0.1" in lines
        assert "ntp server 10.0.0.2" in lines

    def test_snmp_ro_default(self):
        lines = generate_management_cli(snmp={"community": "public"})
        assert "snmp-server community public RO" in lines

    def test_snmp_rw_uppercase(self):
        lines = generate_management_cli(snmp={"community": "private", "access": "rw"})
        assert "snmp-server community private RW" in lines

    def test_snmp_location_and_contact(self):
        lines = generate_management_cli(
            snmp={
                "community": "public",
                "location": "Server Room",
                "contact": "noc@example.com",
            }
        )
        assert "snmp-server community public RO" in lines
        assert "snmp-server location Server Room" in lines
        assert "snmp-server contact noc@example.com" in lines

    def test_snmp_optional_fields_absent_when_not_given(self):
        lines = generate_management_cli(snmp={"community": "public"})
        assert not any("snmp-server location" in l for l in lines)
        assert not any("snmp-server contact" in l for l in lines)

    def test_logging_hosts(self):
        lines = generate_management_cli(logging_hosts=["192.168.1.100"])
        assert "logging host 192.168.1.100" in lines

    def test_logging_multiple_hosts(self):
        lines = generate_management_cli(
            logging_hosts=["192.168.1.100", "192.168.1.101"]
        )
        assert "logging host 192.168.1.100" in lines
        assert "logging host 192.168.1.101" in lines

    def test_clock_timezone(self):
        lines = generate_management_cli(
            clock_timezone={"name": "UTC", "offset": 0}
        )
        assert "clock timezone UTC 0" in lines

    def test_clock_timezone_negative_offset(self):
        lines = generate_management_cli(
            clock_timezone={"name": "EST", "offset": -5}
        )
        assert "clock timezone EST -5" in lines

    def test_full_management_config(self):
        lines = generate_management_cli(
            ntp_servers=["10.0.0.1", "10.0.0.2"],
            snmp={
                "community": "public",
                "access": "ro",
                "location": "DC1",
                "contact": "admin@lab.local",
            },
            logging_hosts=["10.0.0.50"],
            clock_timezone={"name": "UTC", "offset": 0},
        )
        assert "ntp server 10.0.0.1" in lines
        assert "ntp server 10.0.0.2" in lines
        assert "snmp-server community public RO" in lines
        assert "snmp-server location DC1" in lines
        assert "snmp-server contact admin@lab.local" in lines
        assert "logging host 10.0.0.50" in lines
        assert "clock timezone UTC 0" in lines

    def test_no_line_has_leading_space(self):
        lines = generate_management_cli(
            ntp_servers=["10.0.0.1"],
            snmp={"community": "public"},
            logging_hosts=["10.0.0.50"],
            clock_timezone={"name": "UTC", "offset": 0},
        )
        for line in lines:
            assert not line.startswith(" "), f"Unexpected leading space: {line!r}"

    def test_error_on_empty_call(self):
        with pytest.raises(ValueError, match="nothing to configure"):
            generate_management_cli()

    def test_error_on_all_none(self):
        with pytest.raises(ValueError):
            generate_management_cli(
                ntp_servers=None,
                snmp=None,
                logging_hosts=None,
                clock_timezone=None,
            )
