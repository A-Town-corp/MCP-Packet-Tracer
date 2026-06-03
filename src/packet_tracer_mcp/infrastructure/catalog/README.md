# infrastructure/catalog/

Static catalog of devices, cables, aliases, and templates verified against Packet Tracer 8.x. All data is immutable (`frozen=True` in Pydantic models).

This folder is the **source of truth** for which devices, ports, and cables exist in PT.

## Files

### `devices.py` - Device catalog (74 models)

**Pydantic models:**
- `PortSpec` - Port specification: `speed` (PortSpeed), `slot` (int), `full_name` (full str such as "GigabitEthernet0/0")
- `DeviceModel` - Device: `name`, `pt_type` (name in PT), `category` (DeviceCategory), `ports` (list[PortSpec]), `display_name`

**Verified models:**

| Model | Category | Ports | Notes |
|--------|-----------|---------|-------|
| `1841` | router | 2x FastEthernet | |
| `1941` | router | 2x GigabitEthernet | |
| `2811` | router | 2x FastEthernet | |
| `2901` | router | 2x GigabitEthernet | |
| `2911` | router | 3x GigabitEthernet | **Default** |
| `ISR4321` | router | 2x GigabitEthernet (0/0/0, 0/0/1) | |
| `ISR4331` | router | 3x GigabitEthernet (0/0/0-2) | |
| `Router-PT` | router | 2x FastEthernet | Generic |
| `2950-24` | switch | 24x FastEthernet | Basic L2 |
| `2950T-24` | switch | 24x FastEthernet + 2x GigabitEthernet | |
| `2960-24TT` | switch | 24x FastEthernet + 2x GigabitEthernet | **Default** |
| `Switch-PT` | switch | 8x FastEthernet | Generic |
| `3560-24PS` | switch | 24x FastEthernet + 2x GigabitEthernet | L3 |
| `3650-24PS` | switch | 24x FastEthernet + 2x GigabitEthernet | L3 |
| `PC-PT` | pc | 1x FastEthernet0 | |
| `Server-PT` | server | 1x FastEthernet0 | |
| `Laptop-PT` | laptop | 1x FastEthernet0 | |
| `TabletPC-PT` | pc | 1x FastEthernet0 | |
| `SMARTPHONE-PT` | pc | 1x FastEthernet0 | |
| `Printer-PT` | pc | 1x FastEthernet0 | |
| `Cloud-PT` | cloud | 1x Ethernet6 | WAN simulation |
| `AccessPoint-PT` | accesspoint | 1x Port 0 | |
| `AccessPoint-PT-N` | accesspoint | 1x Port 0 | |
| `AccessPoint-PT-AC` | accesspoint | 1x Port 0 | |
| `LAP-PT` | accesspoint | 1x Port 0 | Lightweight AP |
| `Hub-PT` | hub | 8x Port | |
| `5505` | firewall | 8x FastEthernet | Cisco ASA |
| `5506-X` | firewall | 8x GigabitEthernet | Cisco ASA |
| `WLC-PT` | wlc | 8x GigabitEthernet | Wireless controller |
| `WLC-2504` | wlc | 4x GigabitEthernet | |
| `WLC-3504` | wlc | 4x GigabitEthernet | |
| `DSL-Modem-PT` | modem | Ethernet0 + Coaxial0 | |
| `Cable-Modem-PT` | modem | Ethernet0 + Coaxial0 | |

> **Note:** No router has Serial ports by default. Serial requires physical HWIC modules.

**Functions:**
| Function | Signature | Description |
|---------|-------|-------------|
| `resolve_model(name)` | `str -> DeviceModel` | Resolves a name or alias to a model (uses `aliases.py`) |
| `get_ports_by_speed(model, speed)` | `DeviceModel, PortSpeed -> list[PortSpec]` | Filters ports by speed |
| `get_valid_ports(model_name)` | `str -> set[str]` | Set of full names of valid ports |

**Constant:** `ALL_MODELS: dict[str, DeviceModel]` - Dictionary pt_type -> model.

---

### `cables.py` - Cable types and inference rules

**Constants:**
- `CABLE_TYPES` - 15 types: `straight`, `cross`, `roll`, `serial`, `fiber`, `console`, `phone`, `cable`, `coaxial`, `auto`, `wireless`, `octal`, `cellular`, `usb`, `custom_io`
- `CABLE_RULES` - 88 rules as tuples `(category_a, category_b) -> cable_type`

**Main rules:**
| Combination | Cable |
|-------------|-------|
| Router <-> Router | cross |
| Router <-> PC/Server | cross |
| Switch <-> anything | straight |
| Router <-> Cloud | straight |
| Switch <-> AccessPoint | straight |

**Function:**
```python
infer_cable(cat_a: str, cat_b: str) -> str
```
Infers the correct cable given two device categories.

---

### `aliases.py` - Common aliases for models (101 entries)

**Constant:** `MODEL_ALIASES: dict[str, str]`

Maps informal names to catalog models:
```
"router" -> "2911"        "switch" -> "2960-24TT"    "pc" -> "PC-PT"
"server" -> "Server-PT"   "laptop" -> "Laptop-PT"    "cloud" -> "Cloud-PT"
"ap" -> "AccessPoint-PT"  "meraki" -> "Meraki-MX65W" "iot" -> "Thing" ...
```

Covers 101 aliases for all device types. Used by `resolve_model()` in `devices.py` so the LLM can use natural names.

---

### `templates.py` - Topology templates (9 templates)

**Model:** `TemplateSpec`
| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Human-readable name |
| `key` | `TopologyTemplate` | Enum key |
| `description` | `str` | Template description |
| `min_routers` / `max_routers` | `int` | Allowed router limits |
| `defaults` | `dict` | Template default values |
| `requires_wan` | `bool` | Whether a WAN cloud is needed |
| `default_routing` | `RoutingProtocol` | Recommended routing |
| `tags` | `list[str]` | Tags for search |

**Available templates:**
| Key | Name | Routers | Routing | WAN | Description |
|-----|--------|---------|---------|-----|-------------|
| `single_lan` | Single LAN | 1 | static | No | Simple network: 1 router, 1 switch, N PCs |
| `multi_lan` | Multi-LAN | 2-20 | static | No | Chain of routers, each with its own LAN |
| `multi_lan_wan` | Multi-LAN + WAN | 2-20 | static | Yes | Multi-LAN with WAN cloud |
| `star` | Star | 1 | static | No | 1 router with N switches (flat hub & spoke) |
| `hub_spoke` | Hub & Spoke | 2-20 | static | No | 1 hub router + N spoke routers |
| `branch_office` | Branch Office | 2-10 | static | Yes | Central office + branches with WAN |
| `three_router_triangle` | Triangle | 3 | ospf | No | 3 routers with redundancy |
| `router_on_a_stick` | Router on a Stick | 1 | none | No | Inter-VLAN routing |
| `custom` | Custom | 1-20 | static | No | No restrictions |

**Functions:**
- `get_template(key)` -> `TemplateSpec`
- `list_templates()` -> `list[TemplateSpec]`
