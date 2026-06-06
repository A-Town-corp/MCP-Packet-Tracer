# Changelog

All notable changes to this project are documented here. This project adheres to
[Semantic Versioning](https://semver.org/).

## [0.5.0]

First public release.

### Added — live configuration (27 new tools, 30 → 57)
These tools configure devices already on the canvas by talking to the HTTP bridge
directly, so they work on a freshly built topology or one opened by hand. Each one
confirms the change landed in Packet Tracer and returns the exact IOS it sent.

- **Routing:** `pt_apply_ospf`, `pt_apply_rip`, `pt_apply_eigrp`, `pt_apply_bgp`
- **Switching & VLANs:** `pt_create_vlans`, `pt_apply_vtp`, `pt_apply_stp`,
  `pt_configure_etherchannel`, `pt_apply_port_security`, `pt_apply_svi`
- **L3 services:** `pt_add_static_route`, `pt_apply_hsrp`, `pt_apply_dhcp_relay`, `pt_apply_ipv6`
- **Interfaces & WAN:** `pt_configure_interface`, `pt_apply_loopback`,
  `pt_configure_serial`, `pt_apply_gre_tunnel`
- **Security & management:** `pt_apply_device_security`, `pt_apply_management`
- **Universal escape hatch:** `pt_apply_ios` — apply arbitrary IOS lines to any device
- **End devices:** `pt_configure_pc`, `pt_configure_wireless`

### Added — observability
- `pt_run_command`, `pt_get_running_config`, `pt_ping`, `pt_save_project` — read live
  state back from devices, closing the build → configure → verify loop.

### Changed
- Hardened the HTTP bridge request/response handling following a 33-finding
  reliability audit (stale-result draining, deadline-aware long-polling, idempotent
  patch re-application on PT reconnect).
- Packaging metadata completed for distribution (authors, license, classifiers,
  keywords, project URLs, `dev` extra).

### Tests
- 367 tests passing.

## [0.4.0]

Initial pipeline.

- Plan → validate → auto-fix → explain → generate → deploy for Cisco Packet Tracer
  topologies via 30 MCP tools and 5 catalog resources.
- Catalog of 74 device models, 150 modules and cable inference rules.
- Live deploy over the HTTP bridge, plus topology interaction, ACL and NAT/PAT tools.
