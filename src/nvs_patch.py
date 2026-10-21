"""Conservative offline edits of existing unencrypted ESP-IDF NVS entries.

Keeps namespaces, entry allocation, blob chunks and all unrelated bytes intact.
Does not create entries, grow values or erase/compact pages.
"""
from __future__ import annotations
import struct
import zlib


def crc(data):
    return zlib.crc32(data, 0xffffffff)


def entries(raw):
    if len(raw) % 4096:
        raise ValueError('NVS partition is not page aligned')
    for page in range(0, len(raw), 4096):
        status = struct.unpack_from('<I', raw, page)[0]
        if status == 0xffffffff:
            continue
        if status not in (0xfffffffe, 0xfffffffc):
            raise ValueError('Unsupported NVS page status')
        if crc(raw[page+4:page+28]) != struct.unpack_from('<I',raw,page+28)[0]:
            raise ValueError('NVS page CRC mismatch')
        index = 0
        while index < 126:
            state = (raw[page+32+index//4] >> ((index%4)*2)) & 3
            offset = page+64+index*32
            if state != 2:
                index += 1
                continue
            entry = raw[offset:offset+32]
            span = entry[2]
            if not 1 <= span <= 126-index:
                raise ValueError('Invalid NVS entry span')
            if crc(entry[:4]+entry[8:]) != struct.unpack_from('<I',entry,4)[0]:
                raise ValueError('NVS entry CRC mismatch')
            for child in range(index+1,index+span):
                if (raw[page+32+child//4] >> ((child%4)*2)) & 3 != 2:
                    raise ValueError('Incomplete NVS entry')
            key = entry[8:24].split(b'\0')[0].decode('ascii')
            yield offset, entry, key
            index += span


def patch_existing(original: bytes, updates: dict) -> tuple[bytes, list[str]]:
    parsed = list(entries(original))
    namespaces = {e[24]: key for _, e, key in parsed if e[0] == 0 and e[1] == 1}
    result = bytearray(original)
    found, changed = set(), []
    for offset, original_entry, key in parsed:
        target = (namespaces.get(original_entry[0]), key)
        if target not in updates:
            continue
        found.add(target)
        entry = bytearray(original_entry)
        value = updates[target]
        if entry[1] == 0x21 and isinstance(value,str):
            size = struct.unpack_from('<H',entry,24)[0]
            old = original[offset+32:offset+32+size]
            if crc(old) != struct.unpack_from('<I',entry,28)[0]:
                raise ValueError('NVS string CRC mismatch')
            payload = value.encode('utf-8') + b'\0'
            capacity = (entry[2]-1)*32
            if len(payload) > capacity:
                raise ValueError('New string exceeds existing capacity')
            struct.pack_into('<H',entry,24,len(payload))
            struct.pack_into('<I',entry,28,crc(payload))
            result[offset+32:offset+32+capacity] = payload.ljust(capacity,b'\xff')
        elif entry[1] < 0x20 and isinstance(value,int):
            width = entry[1] & 15
            entry[24:24+width] = value.to_bytes(width,'little',signed=bool(entry[1]&0x10))
        else:
            raise ValueError('Unsupported entry type for edit')
        struct.pack_into('<I',entry,4,crc(entry[:4]+entry[8:]))
        result[offset:offset+32] = entry
        changed.append(':'.join(target))
    if found != set(updates):
        raise ValueError('Missing NVS keys: '+str(set(updates)-found))
    list(entries(result))
    return bytes(result), changed
