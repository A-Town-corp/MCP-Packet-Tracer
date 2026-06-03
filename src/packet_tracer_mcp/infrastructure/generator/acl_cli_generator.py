"""IOS CLI generator for ACLs.

Produces the `access-list` and `ip access-group` commands that are applied via
`configureIosDevice` through the bridge. The output can be consumed in
two ways:

  1. `generate_acl_cli(plan)` -> list[str] of IOS lines for review.
  2. `build_configure_payload(plan, binding=None)` -> a fully formatted
     string with internal \\n, ready to inject as the second argument
     of configureIosDevice. Important: this string MUST travel inside
     a single JS statement (no \\n in the JS code), because PT's
     executeCode() strips the \\n from JS source code.
"""

from __future__ import annotations
from ...domain.models.acls import ACLPlan, ACLEntry, ACLBinding


def generate_acl_cli(plan: ACLPlan) -> list[str]:
    """Generate the `access-list ...` lines for an ACLPlan.

    Does not include `enable`, `configure terminal` or `end`. Only the
    intermediate lines that define the ACL.
    """
    lines: list[str] = []
    is_named = not plan.name_or_number.strip().isdigit()
    if is_named:
        # Named ACL: `ip access-list standard|extended NAME` + indented entries.
        # The flat `access-list NAME ...` form is INVALID IOS for non-numeric ids.
        lines.append(f"ip access-list {plan.acl_type} {plan.name_or_number}")
        for entry in plan.entries:
            if entry.remark:
                lines.append(f" remark {entry.remark}")
            rendered = _render_entry(plan.name_or_number, plan.acl_type, entry, is_named=True)
            # A named-ACL entry may carry an explicit sequence number, which goes
            # before the action ( "<seq> permit ..." ). Honor it instead of
            # silently dropping the user's ordering.
            if entry.sequence is not None:
                rendered = f"{entry.sequence} {rendered}"
            lines.append(" " + rendered)
        lines.append("exit")
    else:
        for entry in plan.entries:
            if entry.remark:
                lines.append(f"access-list {plan.name_or_number} remark {entry.remark}")
            lines.append(_render_entry(plan.name_or_number, plan.acl_type, entry, is_named=False))
    return lines


def generate_acl_binding_cli(binding: ACLBinding) -> list[str]:
    """Generate the lines to apply an ACL to an interface.

    Output:
        interface <iface>
         ip access-group <id> <direction>
         exit
    """
    return [
        f"interface {binding.interface}",
        f" ip access-group {binding.acl_id} {binding.direction}",
        " exit",
    ]


def build_configure_payload(plan: ACLPlan, binding: ACLBinding | None = None) -> str:
    """Build the full string for configureIosDevice.

    Structure:
        enable
        configure terminal
        <access-list lines>
        [interface ... / ip access-group ... / exit]
        end
        write memory

    The lines are joined with `\\n` (real newlines). This string IS PASSED
    as an argument to configureIosDevice; the `\\n` here are NOT the `\\n`
    of the JS code (those get stripped by executeCode), but characters
    inside a string that IOS interprets as Enter.
    """
    lines: list[str] = ["enable", "configure terminal"]
    lines.extend(generate_acl_cli(plan))
    if binding is not None:
        lines.extend(generate_acl_binding_cli(binding))
    lines.append("end")
    lines.append("write memory")
    return "\n".join(lines)


def build_remove_payload(router: str, name_or_number: str, binding_interface: str = "", direction: str = "in", acl_type: str = "extended") -> str:
    """Build commands to remove an ACL (and its binding if applicable).

    Numbered ACL -> `no access-list <num>`.
    Named ACL    -> `no ip access-list <standard|extended> <name>` (the numbered
                   form is invalid IOS for a non-numeric id). `acl_type` is
                   required for the named case since it can't be inferred.
    """
    lines: list[str] = ["enable", "configure terminal"]
    if binding_interface:
        lines.append(f"interface {binding_interface}")
        lines.append(f" no ip access-group {name_or_number} {direction}")
        lines.append(" exit")
    if name_or_number.strip().isdigit():
        lines.append(f"no access-list {name_or_number}")
    else:
        # A named ACL lives in a type-scoped namespace and the `no ip access-list
        # <type> NAME` form must name the EXISTING type. The removal path can't
        # know whether the caller created it standard or extended, so emit both;
        # the one that doesn't match is a harmless no-op in IOS/PT. (acl_type is
        # kept for signature compatibility but no longer trusted as a guess.)
        lines.append(f"no ip access-list standard {name_or_number}")
        lines.append(f"no ip access-list extended {name_or_number}")
    lines.append("end")
    lines.append("write memory")
    return "\n".join(lines)


# ----------------------------------------------------------------------
# Private helpers
# ----------------------------------------------------------------------

def _render_entry(acl_id: str, acl_type: str, entry: ACLEntry, is_named: bool = False) -> str:
    """Render an entry as an IOS line.

    Numbered ACL -> `access-list <id> <action> ...`.
    Named ACL    -> `<action> ...` (the `ip access-list <type> <name>` header
                   and indentation are added by generate_acl_cli).
    """
    parts: list[str] = [] if is_named else [f"access-list {acl_id}"]

    parts.append(entry.action)

    if acl_type == "standard":
        # Standard: `access-list N {permit|deny} <source>`
        parts.append(entry.source)
    else:
        # Extended: `access-list N {permit|deny} <protocol> <source> [src-port] <dest> [dst-port] [icmp-type] [flags] [log]`
        parts.append(entry.protocol)
        parts.append(entry.source)
        if entry.source_port_op:
            parts.append(_render_port(entry.source_port_op, entry.source_port, entry.source_port_end))
        parts.append(entry.destination if entry.destination else "any")
        if entry.dest_port_op:
            parts.append(_render_port(entry.dest_port_op, entry.dest_port, entry.dest_port_end))
        if entry.icmp_type:
            parts.append(entry.icmp_type)
        for flag in entry.tcp_flags:
            parts.append(flag)

    if entry.log:
        parts.append("log")

    return " ".join(parts)


def _render_port(op: str, port: int | None, port_end: int | None) -> str:
    if op == "range":
        return f"range {port} {port_end}"
    return f"{op} {port}"
