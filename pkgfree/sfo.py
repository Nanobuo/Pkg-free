"""Minimal param.sfo reader."""

import struct

SFO_MAGIC = b"\x00PSF"


def parse_sfo(data: bytes) -> dict:
    if len(data) < 20 or data[:4] != SFO_MAGIC:
        raise ValueError("param.sfo non valido")
    _, key_table, data_table, count = struct.unpack_from("<IIII", data, 4)
    result = {}
    for i in range(count):
        key_off, fmt, length, _max_len, data_off = struct.unpack_from("<HHIII", data, 20 + i * 16)
        key_start = key_table + key_off
        key = data[key_start:data.index(b"\x00", key_start)].decode("utf-8", "replace")
        raw = data[data_table + data_off:data_table + data_off + length]
        if fmt == 0x0404:
            result[key] = struct.unpack("<I", raw[:4])[0]
        else:
            result[key] = raw.split(b"\x00", 1)[0].decode("utf-8", "replace")
    return result
