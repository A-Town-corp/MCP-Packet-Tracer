"""Offline canvas-note injection for Packet Tracer .pkt files.

PT's scripting API can't place canvas text notes (the draw tools need live mouse
input), so we add them OFFLINE: decrypt the .pkt -> insert <NOTE> elements into
the logical workspace's canvas <NOTES> container -> re-encrypt. Open the result
in PT and the notes are there.

Canvas NOTE schema (verified from a bundled PT activity):
  <NOTE uuid="{...}"><X>391</X><Y>29</Y><Z>40000</Z>
   <TEXT translate="true">the text</TEXT><NOTECLUSTERID>1-1</NOTECLUSTERID></NOTE>

The canvas <NOTES> container is the one immediately AFTER <POLYGONS> in the
logical-workspace block (siblings: LINES/RECTANGLES/ELLIPSES/POLYGONS/NOTES) -
NOT the unrelated <NOTES> blocks inside the options/activity-wizard sections.
"""
from __future__ import annotations
import re
import os
import sys
import uuid as _uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pkt_decrypt import decrypt_pkt   # noqa: E402
from pkt_encrypt import encrypt_pkt   # noqa: E402


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def make_ellipse(x1: int, y1: int, x2: int, y2: int, rgb=(255, 0, 0),
                 filled: bool = False, cluster: str = "1-1") -> str:
    """Render one <ELLIPSE> (a colored circle/oval) bounded by (x1,y1)-(x2,y2).

    rgb is the outline (and fill) color. By default the circle is an outline
    only (filled=False) so it frames devices without hiding them.
    """
    r, g, b = rgb
    hexc = f"#{r:02x}{g:02x}{b:02x}"
    return (
        f'<ELLIPSE uuid="{{{_uuid.uuid4()}}}">'
        f"<TopLeftX>{int(x1)}</TopLeftX><TopLeftY>{int(y1)}</TopLeftY>"
        f"<BottomRightX>{int(x2)}</BottomRightX><BottomRightY>{int(y2)}</BottomRightY>"
        f"<Color><Red>{r}</Red><Green>{g}</Green><Blue>{b}</Blue></Color>"
        f'<Filled OUTLINECOLOR="{hexc}" OUTLINED="true">{1 if filled else 0}</Filled>'
        f"<ELLIPSECLUSTERID>{cluster}</ELLIPSECLUSTERID></ELLIPSE>"
    )


def inject_ellipses_into_xml(xml: bytes, ellipses: list[str]) -> bytes:
    """Insert pre-rendered <ELLIPSE> strings into the canvas <ELLIPSES> container
    (the geometry one, which follows <RECTANGLES> after </CLUSTERS>)."""
    s = xml.decode("utf-8")
    payload = "".join(ellipses)
    rect = re.search(r"<RECTANGLES\b[^>]*/?>", s)
    start = rect.end() if rect else 0
    m_empty = re.compile(r"<ELLIPSES\s*/>").search(s, start)
    m_open = re.compile(r"<ELLIPSES\s*>(.*?)</ELLIPSES>", re.S).search(s, start)
    cand = [m for m in (m_empty, m_open) if m]
    if not cand:
        raise ValueError("no canvas <ELLIPSES> container found after <RECTANGLES>")
    m = min(cand, key=lambda mm: mm.start())
    if m is m_empty:
        new_block = f"<ELLIPSES>{payload}</ELLIPSES>"
    else:
        new_block = f"<ELLIPSES>{m.group(1)}{payload}</ELLIPSES>"
    return (s[:m.start()] + new_block + s[m.end():]).encode("utf-8")


def make_note(text: str, x: int, y: int, z: int = 40000, cluster: str = "1-1") -> str:
    """Render one <NOTE> element (a canvas text label at x,y)."""
    u = "{" + str(_uuid.uuid4()) + "}"
    return (
        f'<NOTE uuid="{u}"><X>{int(x)}</X><Y>{int(y)}</Y><Z>{int(z)}</Z>'
        f'<TEXT translate="true">{_esc(text)}</TEXT>'
        f'<NOTECLUSTERID>{cluster}</NOTECLUSTERID></NOTE>'
    )


def inject_notes_into_xml(xml: bytes, notes: list[dict]) -> bytes:
    """Insert notes into the CANVAS <NOTES> container of a decrypted .pkt XML.

    `notes` = [{"text": "...", "x": 200, "y": 30, "z": 40000 (opt)}, ...].
    """
    s = xml.decode("utf-8")
    payload = "".join(make_note(**n) for n in notes)

    # The canvas NOTES container is the <NOTES> in the logical-workspace block,
    # which sits immediately after </GRID_COLOR> (the workspace display settings).
    # This reliably distinguishes it from the unrelated <NOTES> blocks inside the
    # simulation-options / activity-wizard sections.
    anchor = re.search(r"</GRID_COLOR>\s*", s)
    if not anchor:
        raise ValueError("no </GRID_COLOR> anchor - not a logical-workspace .pkt XML?")
    start = anchor.end()
    m_empty = re.match(r"<NOTES\s*/>", s[start:])
    m_open = re.match(r"<NOTES\s*>(.*?)</NOTES>", s[start:], re.S)
    if m_empty:
        new_block = f"<NOTES>{payload}</NOTES>"
        a, b = start, start + m_empty.end()
    elif m_open:
        new_block = f"<NOTES>{m_open.group(1)}{payload}</NOTES>"
        a, b = start, start + m_open.end()
    else:
        raise ValueError("no <NOTES> container immediately after </GRID_COLOR>")
    new_s = s[:a] + new_block + s[b:]
    return new_s.encode("utf-8")


def inject_notes_into_pkt(in_path: str, out_path: str, notes: list[dict]) -> dict:
    """Decrypt in_path, inject notes, re-encrypt to out_path."""
    xml = decrypt_pkt(in_path)
    new_xml = inject_notes_into_xml(xml, notes)
    data = encrypt_pkt(new_xml)
    with open(out_path, "wb") as f:
        f.write(data)
    return {"in": in_path, "out": out_path, "notes": len(notes),
            "xml_before": len(xml), "xml_after": len(new_xml), "pkt_bytes": len(data)}


if __name__ == "__main__":
    import argparse
    import json

    ap = argparse.ArgumentParser(
        description="Inject canvas text notes into a Packet Tracer .pkt (offline).")
    ap.add_argument("input", help="source .pkt")
    ap.add_argument("output", help="output .pkt (open this in PT)")
    ap.add_argument("-n", "--note", action="append", default=[], metavar="X,Y,TEXT",
                    help="a note as 'X,Y,Text...' (repeatable), e.g. -n '60,20,Core Layer'")
    ap.add_argument("--notes-json", help="path to a JSON list of {text,x,y[,z]} notes")
    args = ap.parse_args()

    notes = []
    if args.notes_json:
        notes.extend(json.load(open(args.notes_json)))
    for spec in args.note:
        x, y, text = spec.split(",", 2)
        notes.append({"text": text, "x": int(x), "y": int(y)})
    if not notes:
        ap.error("provide at least one --note X,Y,Text or --notes-json")
    print(json.dumps(inject_notes_into_pkt(args.input, args.output, notes), indent=2))
