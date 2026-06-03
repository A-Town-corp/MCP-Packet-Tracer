"""Shared helpers for "apply IOS config to an existing device" use cases.

Features like ACL, NAT, SVI, EtherChannel, HSRP, static routes, DHCP relay and
IPv6 all follow the same shape: build a list of IOS body lines, wrap them with
enable/configure terminal/.../end/write memory, send through the bridge via
configureIosDevice, and confirm success with reportResult so the MCP layer can
report whether PT actually applied the config.
"""

from __future__ import annotations
import json
from typing import Callable


def _escape_js(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def build_ios_payload(body_lines: list[str]) -> str:
    """Wrap body IOS lines with enable/configure terminal/end/write memory.

    `body_lines` are the config lines WITHOUT the enable/conf t/end wrapper
    (e.g. ["interface Vlan10", " ip address 10.0.0.1 255.255.255.0", " exit"]).
    """
    return "\n".join(["enable", "configure terminal", *body_lines, "end", "write memory"])


def build_configure_js(device: str, ios_payload: str, confirm: bool = True) -> str:
    """Wrap an IOS payload in a single-line configureIosDevice JS call.

    The \\n inside the payload are string-literal escapes (they survive
    executeCode, which strips real source-line breaks). With confirm=True the
    call reports {ok: <bool>} so the caller can verify real application.
    """
    safe_device = _escape_js(device)
    safe_payload = (
        ios_payload
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
    )
    if confirm:
        return (
            f'var __ok = configureIosDevice("{safe_device}", "{safe_payload}"); '
            f'reportResult(JSON.stringify({{ok: __ok === true}}));'
        )
    return f'configureIosDevice("{safe_device}", "{safe_payload}");'


def parse_ok(res: str | None) -> bool | None:
    """Interpret the bridge {ok: bool} reply. None if there was no response."""
    if res is None:
        return None
    try:
        return bool(json.loads(res).get("ok"))
    except Exception:
        return None


def apply_ios(
    device: str,
    body_lines: list[str],
    confirm_send: Callable[[str], str | None] | None = None,
    dry_run: bool = False,
) -> dict:
    """Assemble the payload and (optionally) apply it via the confirming bridge.

    Returns a dict with: cli_lines, ios_payload, js_payload, sent, applied,
    dry_run - the common shape the MCP tools serialize.
    """
    ios_payload = build_ios_payload(body_lines)
    js_payload = build_configure_js(device, ios_payload, confirm=True)

    sent = False
    applied: bool | None = None
    if not dry_run and confirm_send is not None:
        res = confirm_send(js_payload)
        # `sent` means "dispatched to the bridge", `applied` means "PT confirmed".
        # A result-channel timeout (res is None) still means the command was
        # queued and very likely applied, so report sent=True/applied=None
        # (-> "sent but not confirmed; verify") instead of sent=False, which
        # reads as "nothing happened" and invites a double-apply.
        sent = True
        applied = parse_ok(res)

    return {
        "cli_lines": body_lines,
        "ios_payload": ios_payload,
        "js_payload": js_payload,
        "sent": sent,
        "applied": applied,
        "dry_run": dry_run,
    }
