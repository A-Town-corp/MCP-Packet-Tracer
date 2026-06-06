"""Decrypt Cisco Packet Tracer 9.0 .pkt/.pka files to XML (the "pka2xml" scheme).

Pipeline (decrypt_pka in pka2xml):
  1. Stage-1 deobfuscation: reverse byte order + XOR
        out[i] = data[len-1-i] ^ ((len - i*len) & 0xFF)
  2. Twofish-EAX decrypt   key=16x0x89  iv/nonce=16x0x10  (tag appended at end)
  3. Stage-3 deobfuscation: out[i] = data[i] ^ ((len - i) & 0xFF)
  4. Qt qUncompress (4-byte BE size header + zlib stream)  -- exactly ONCE

Requires the `twofish` package (`pip install twofish`, or `pip install -e ".[offline]"`).
"""
import os
import sys, struct, zlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import twofish
from eax import eax_decrypt

KEY = bytes([137] * 16)   # 0x89 x16
IV  = bytes([16] * 16)    # 0x10 x16

def stage1(buf):
    n = len(buf); out = bytearray(n)
    for i in range(n):
        out[i] = buf[n - 1 - i] ^ ((n - i * n) & 0xFF)
    return bytes(out)

def stage3(buf):
    n = len(buf); out = bytearray(n)
    for i in range(n):
        out[i] = buf[i] ^ ((n - i) & 0xFF)
    return bytes(out)

def qUncompress(buf):
    # Qt format: 4-byte big-endian uncompressed size + raw zlib stream
    if len(buf) < 4:
        return b''
    expected = struct.unpack('>I', buf[:4])[0]
    out = zlib.decompress(buf[4:])
    if len(out) != expected:
        raise ValueError(f"qUncompress size mismatch: header={expected} actual={len(out)}")
    return out

def decrypt_pkt(path_or_bytes):
    raw = path_or_bytes if isinstance(path_or_bytes, (bytes, bytearray)) else open(path_or_bytes, 'rb').read()
    s1 = stage1(raw)
    tf = twofish.Twofish(KEY)
    pt, tag_ok, _ = eax_decrypt(tf.encrypt, IV, s1)
    if not tag_ok:
        raise ValueError("EAX authentication tag verification FAILED")
    s3 = stage3(pt)
    return qUncompress(s3)

if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else \
        (sys.argv[1] if len(sys.argv)>1 else 'sample.pkt')
    xml = decrypt_pkt(path)
    print(f"Decrypted {path} -> {len(xml)} bytes XML")
    print("First 120 bytes:", xml[:120])
    out = path + '.xml'
    open(out, 'wb').write(xml)
    print(f"Wrote {out}")
