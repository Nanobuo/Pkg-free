"""Builds small synthetic fake PKGs for tests (the inverse of pkgfree.pkg)."""

import hashlib
import os
import struct
import zlib

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from pkgfree import crypto, keys

BS = 0x10000


def _rsa_encrypt(msg: bytes, n: int, e: int) -> bytes:
    pad_len = 256 - 3 - len(msg)
    padding = bytes((b % 255) + 1 for b in os.urandom(pad_len))
    em = b"\x00\x02" + padding + b"\x00" + msg
    return pow(int.from_bytes(em, "big"), e, n).to_bytes(256, "big")


def _aes_cbc_encrypt(iv_key: bytes, data: bytes) -> bytes:
    enc = Cipher(algorithms.AES(iv_key[16:32]), modes.CBC(iv_key[:16])).encryptor()
    return enc.update(data) + enc.finalize()


def make_sfo(values: dict) -> bytes:
    keys_sorted = sorted(values)
    key_table = b""
    data_table = b""
    index = b""
    for k in keys_sorted:
        v = values[k]
        if isinstance(v, int):
            raw, fmt = struct.pack("<I", v), 0x0404
            length = max_len = 4
        else:
            raw = v.encode() + b"\x00"
            fmt, length = 0x0204, len(raw)
            max_len = (len(raw) + 3) & ~3
            raw = raw.ljust(max_len, b"\x00")
        index += struct.pack("<HHIII", len(key_table), fmt, length, max_len, len(data_table))
        key_table += k.encode() + b"\x00"
        data_table += raw
    key_table = key_table.ljust((len(key_table) + 3) & ~3, b"\x00")
    key_start = 20 + len(index)
    data_start = key_start + len(key_table)
    hdr = b"\x00PSF" + struct.pack("<IIII", 0x101, key_start, data_start, len(keys_sorted))
    return hdr + index + key_table + data_table


def _dirent(ino: int, typ: int, name: str) -> bytes:
    nb = name.encode()
    size = (16 + len(nb) + 1 + 7) & ~7
    return struct.pack("<iiii", ino, typ, len(nb), size) + nb.ljust(size - 16, b"\x00")


def _build_inner(files: dict) -> bytes:
    """files: {'dir/name': bytes}. Returns the decompressed inner PFS image."""
    # Build directory tree.
    tree = {}
    for path, data in files.items():
        parts = path.split("/")
        node = tree
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = data

    inodes = []  # (mode, size, blocks, loc)
    blocks = []  # list of block payloads (bytes <= BS); index 0 -> block 2

    def alloc(data: bytes) -> tuple[int, int]:
        n = max(1, (len(data) + BS - 1) // BS)
        loc = 2 + len(blocks)
        for i in range(n):
            blocks.append(data[i * BS:(i + 1) * BS])
        return loc, n

    def new_inode() -> int:
        inodes.append(None)
        return len(inodes) - 1

    def build_dir(node: dict, ino: int, parent: int) -> None:
        ents = _dirent(ino, 4, ".") + _dirent(parent, 5, "..")
        children = []
        for name, val in node.items():
            child = new_inode()
            children.append((name, val, child))
            ents += _dirent(child, 3 if isinstance(val, dict) else 2, name)
        for name, val, child in children:
            if isinstance(val, dict):
                build_dir(val, child, ino)
            else:
                loc, n = alloc(val)
                inodes[child] = (0x8000 | 0o444, len(val), n, loc)
        loc, n = alloc(ents)
        inodes[ino] = (0x4000 | 0o555, len(ents), n, loc)

    superroot = new_inode()
    fpt = new_inode()
    uroot = new_inode()
    # Like real images, the superroot has no "." / ".." entries.
    sr_ents = _dirent(fpt, 2, "flat_path_table") + _dirent(uroot, 3, "uroot")
    fpt_loc, fpt_n = alloc(b"\x00" * 16)
    inodes[fpt] = (0x8000, 16, fpt_n, fpt_loc)
    build_dir(tree, uroot, superroot)
    loc, n = alloc(sr_ents)
    inodes[superroot] = (0x4000, len(sr_ents), n, loc)

    assert len(inodes) * 0xA8 <= BS
    sb = bytearray(BS)
    struct.pack_into("<qqq", sb, 0, 1, 20130315, 0)
    struct.pack_into("<H", sb, 0x1C, 0)
    struct.pack_into("<i", sb, 0x20, BS)
    struct.pack_into("<q", sb, 0x30, len(inodes))
    struct.pack_into("<q", sb, 0x48, superroot)
    ib = bytearray(BS)
    for i, (mode, size, nblk, loc) in enumerate(inodes):
        off = i * 0xA8
        struct.pack_into("<HHI", ib, off, mode, 1, 0)
        struct.pack_into("<qq", ib, off + 8, size, size)
        struct.pack_into("<II", ib, off + 0x60, nblk, loc)
    image = bytes(sb) + bytes(ib) + b"".join(b.ljust(BS, b"\x00") for b in blocks)
    return image


def _build_pfsc(inner: bytes) -> bytes:
    n = len(inner) // BS
    hdr_size = 0x400
    payloads = []
    for i in range(n):
        blk = inner[i * BS:(i + 1) * BS]
        comp = zlib.compress(blk)
        payloads.append(comp if len(comp) < BS else blk)
    data_start = hdr_size + (n + 1) * 8
    data_start = (data_start + 0xF) & ~0xF
    offsets = [data_start]
    for p in payloads:
        offsets.append(offsets[-1] + len(p))
    hdr = bytearray(hdr_size)
    hdr[0:4] = b"PFSC"
    struct.pack_into("<i", hdr, 0x0C, BS)
    struct.pack_into("<Q", hdr, 0x10, BS)
    struct.pack_into("<Q", hdr, 0x18, hdr_size)
    struct.pack_into("<Q", hdr, 0x20, data_start)
    struct.pack_into("<Q", hdr, 0x28, len(inner))
    table = b"".join(struct.pack("<Q", o) for o in offsets).ljust(data_start - hdr_size, b"\x00")
    return bytes(hdr) + table + b"".join(payloads)


def build_pkg(path: str, content_id: str, sfo: dict, files: dict,
              content_flags: int = 0, with_pfs: bool = True, new_crypt: bool = False) -> bytes:
    dk3 = os.urandom(32)
    ekpfs = os.urandom(32)
    seed = os.urandom(16)

    sfo_bytes = make_sfo(sfo)
    np_plain = b"NPTITLE-DATA-123" * 4

    # entries: (id, flags1, flags2, data_fn)
    entry_specs = [
        (0x10, 0, 0),
        (0x20, 0, 0),
        (0x402, 0x80000000, 0x3000),
        (0x1000, 0, 0),
        (0x1200, 0, 0),
    ]
    table_off = 0x2000
    data_off = table_off + 32 * len(entry_specs)
    sizes = {0x10: 32 + 7 * 32 + 7 * 256, 0x20: 256, 0x402: len(np_plain),
             0x1000: len(sfo_bytes), 0x1200: 8}
    raws, offsets = {}, {}
    cur = data_off
    for eid, f1, f2 in entry_specs:
        offsets[eid] = cur
        raws[eid] = struct.pack(">IIIIII", eid, 0, f1, f2, cur, sizes[eid]) + b"\x00" * 8
        cur = (cur + sizes[eid] + 15) & ~15

    data = {}
    ek = bytearray(sizes[0x10])
    ek[32 + 7 * 32 + 3 * 256:32 + 7 * 32 + 4 * 256] = _rsa_encrypt(
        dk3, keys.PKG_DERIVED_KEY3_N, keys.PKG_DERIVED_KEY3_E)
    data[0x10] = bytes(ek)
    img = _rsa_encrypt(ekpfs, keys.FAKE_N, keys.FAKE_E)
    data[0x20] = _aes_cbc_encrypt(hashlib.sha256(raws[0x20][:24] + b"\x00" * 8 + dk3).digest(), img)
    data[0x402] = _aes_cbc_encrypt(hashlib.sha256(raws[0x402] + dk3).digest(), np_plain)
    data[0x1000] = sfo_bytes
    data[0x1200] = b"ICONDATA"

    pfs_off = (cur + 0xFFFF) & ~0xFFFF
    if with_pfs:
        pfsc = _build_pfsc(_build_inner(files))
        outer = bytearray(0x20000) + pfsc
        outer += b"\x00" * ((-len(outer)) % 0x1000)
        struct.pack_into("<H", outer, 0x1C, 0x4 | 0x8)
        outer[0x370:0x380] = seed
        data_key, tweak_key = crypto.pfs_gen_crypto_key(ekpfs, seed, new_crypt)
        key = algorithms.AES(data_key + tweak_key)
        for s in range(0x10, len(outer) // 0x1000):
            e = Cipher(key, modes.XTS(s.to_bytes(16, "little"))).encryptor()
            outer[s * 0x1000:(s + 1) * 0x1000] = e.update(bytes(outer[s * 0x1000:(s + 1) * 0x1000]))
        pfs_size = len(outer)
    else:
        outer = b""
        pfs_off = pfs_size = 0

    total = max(cur, pfs_off + pfs_size)
    buf = bytearray(total)
    struct.pack_into(">I", buf, 0, 0x7F434E54)
    struct.pack_into(">I", buf, 0x10, len(entry_specs))
    struct.pack_into(">I", buf, 0x18, table_off)
    buf[0x40:0x40 + len(content_id)] = content_id.encode()
    struct.pack_into(">II", buf, 0x74, 0x1A, content_flags)
    pfs_flags = 0x80000000000003CC | (0x2000000000000000 if new_crypt else 0)
    struct.pack_into(">QQQ", buf, 0x408, pfs_flags, pfs_off, pfs_size)
    struct.pack_into(">Q", buf, 0x430, total)
    for i, (eid, _, _) in enumerate(entry_specs):
        buf[table_off + i * 32:table_off + (i + 1) * 32] = raws[eid]
        buf[offsets[eid]:offsets[eid] + sizes[eid]] = data[eid]
    if with_pfs:
        buf[pfs_off:pfs_off + pfs_size] = outer
    with open(path, "wb") as f:
        f.write(buf)
    return np_plain
