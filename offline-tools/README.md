# Offline Tools — Packet Tracer file-format utilities

Standalone Python utilities for reading, writing and authoring Cisco Packet
Tracer's encrypted file formats **without** running Packet Tracer. They complement
the MCP server: the MCP drives a *live* PT instance, while these manipulate the
files directly (handy for batch edits, CI, or adding canvas annotations the live
scripting API can't create).

These build on the publicly documented PT container formats (same scheme as the
well-known `pka2xml` project). Cipher keys are the fixed constants PT ships with;
the CAST-256 S-boxes are the standard public RFC 2612 values.

## Contents

| File | What it does |
|------|--------------|
| `cast256.py` | Self-contained CAST-256 (RFC 2612) block cipher + EAX mode. Passes the RFC test vectors. |
| `eax.py` | EAX authenticated-encryption mode helper. |
| `pts_decrypt.py` / `pts_encrypt.py` | Decrypt/re-encrypt `.pts` **extension modules** (CAST-256-EAX → double zlib). Bit-perfect round-trip. |
| `pts_builder.py` | Author a brand-new `.pts` extension module from scratch (scripts + interfaces + privileges) — "NetPilot style". |
| `pkt_decrypt.py` / `pkt_encrypt.py` | Decrypt/re-encrypt `.pkt` / `.pka` **save files** (Twofish-EAX with XOR pre/post stages → qUncompress). Bit-perfect round-trip. |
| `pkt_inject_note.py` | Inject canvas **notes** (text labels) and colored **ellipses** (e.g. per-VLAN circles) into a `.pkt` offline. |
| `example_build5.py` | Example: generate 5 distinct company topologies as MCP deploy plans. |

## Install

The `.pts` tools and `pkt_inject_note` need only the standard library.
The `.pkt` crypto (`pkt_decrypt`/`pkt_encrypt`, and therefore `pkt_inject_note`)
needs Twofish:

```bash
pip install twofish
```

## Usage

```python
# --- .pts extension module: decrypt, edit, re-encrypt ---
from pts_decrypt import decrypt_pts
from pts_encrypt import encrypt_pts
xml = decrypt_pts("MyExtension.pts")            # -> bytes (XML)
open("MyExtension.pts", "wb").write(encrypt_pts(xml))

# --- author a new .pts from scratch ---
from pts_builder import build_pts
build_pts("HelloExt.pts", name="HelloExt", module_id="com.acme.hello",
          author="me", scripts={"main.js": "reportResult('hi');"})

# --- .pkt save file: decrypt to XML ---
from pkt_decrypt import decrypt_pkt
xml = decrypt_pkt("MyNetwork.pkt")              # -> bytes (XML)

# --- annotate a .pkt offline (notes + colored VLAN circles) ---
from pkt_inject_note import inject_notes_into_pkt   # see file for the ellipse API
inject_notes_into_pkt("in.pkt", "out.pkt",
    [{"text": "Core Layer", "x": 200, "y": 40}])
```

Each module also has a small `__main__` demo: `python pts_decrypt.py <file.pts>`.

## Note

These tools are for interoperability, education and automation around your own
Packet Tracer projects. Packet Tracer itself is Cisco software — its binaries and
copyrighted sample files are **not** included in this repository.
