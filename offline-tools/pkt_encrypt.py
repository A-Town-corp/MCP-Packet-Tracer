"""Encrypt XML back into a Cisco Packet Tracer 9.0 .pkt/.pka file (inverse of pkt_decrypt).

Inverse pipeline:
  1. qCompress    : 4-byte BE size header + zlib stream
  2. Stage-3 XOR  : out[i] = data[i] ^ ((len - i) & 0xFF)        (self-inverse)
  3. Twofish-EAX encrypt  key=16x0x89 iv=16x0x10  -> ciphertext + 16-byte tag
  4. Stage-1 obfuscation (inverse of the reverse+XOR):
        for i: out[len-1-i] = data[i] ^ ((len - i*len) & 0xFF)

Note: zlib compression is not guaranteed byte-identical to Qt's deflate, so the
re-encrypted file may differ byte-for-byte from the original. Correctness criterion
is that a re-decrypt yields the identical XML (and a real Packet Tracer can open it).
"""
import os
import sys, struct, zlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import twofish
from eax import eax_encrypt
from pkt_decrypt import KEY, IV, stage1, stage3, decrypt_pkt

def stage1_inverse(buf):
    # inverse of stage1: stage1 maps out[i]=in[n-1-i]^k(i). Inverse: out[n-1-i]=in[i]^k(i)
    n = len(buf); out = bytearray(n)
    for i in range(n):
        out[n - 1 - i] = buf[i] ^ ((n - i * n) & 0xFF)
    return bytes(out)

def qCompress(data, level=6):
    return struct.pack('>I', len(data)) + zlib.compress(data, level)

def encrypt_pkt(xml_bytes):
    a = qCompress(xml_bytes)
    b = stage3(a)                          # stage3 is its own inverse
    tf = twofish.Twofish(KEY)
    c = eax_encrypt(tf.encrypt, IV, b)     # ciphertext + 16-byte tag
    d = stage1_inverse(c)
    return d

def _selftest_xors():
    for n in (1, 2, 15, 16, 17, 1000, 50007):
        x = bytes((i * 37 + 11) & 0xFF for i in range(n))
        assert stage1_inverse(stage1(x)) == x, f"stage1 inverse fail n={n}"
        assert stage1(stage1_inverse(x)) == x, f"stage1 inverse2 fail n={n}"
        assert stage3(stage3(x)) == x, f"stage3 self-inverse fail n={n}"
    print("XOR inverse self-tests: PASS")

if __name__ == '__main__':
    _selftest_xors()
    sample = (sys.argv[1] if len(sys.argv)>1 else 'sample.pkt')
    print(f"\nRound-trip test on {sample}")
    orig_raw = open(sample, 'rb').read()
    xml = decrypt_pkt(orig_raw)
    print(f"  decrypt: {len(xml)} bytes XML, starts {xml[:20]!r}")
    re_enc = encrypt_pkt(xml)
    print(f"  re-encrypt: {len(re_enc)} bytes (original file {len(orig_raw)} bytes)")
    xml2 = decrypt_pkt(re_enc)
    print(f"  re-decrypt: {len(xml2)} bytes XML")
    print(f"  XML round-trip matches original: {xml2 == xml}")
    print(f"  re-encrypted bytes identical to original file: {re_enc == orig_raw}")
    assert xml2 == xml, "ROUND-TRIP FAILED"
    print("\nROUND-TRIP SELF-TEST: PASS")
