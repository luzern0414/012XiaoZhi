import struct
import zlib
import pytest
from src.nvs_patch import patch_existing


def fixture():
    b = bytearray(b'\xff' * 8192)
    b[:4] = struct.pack('<I', 0xfffffffe)
    b[4:8] = bytes(4)
    b[8] = 0xfe
    b[28:32] = struct.pack('<I', zlib.crc32(b[4:28], 0xffffffff))
    def put(i, ns, typ, key, value, span=1):
        off = 64 + i * 32
        e = bytearray(b'\xff' * 32)
        e[:4] = bytes([ns, typ, span, 0xff])
        e[8:24] = key.encode().ljust(16, b'\0')
        e[24:24+len(value)] = value
        e[4:8] = struct.pack('<I', zlib.crc32(e[:4]+e[8:],0xffffffff))
        b[off:off+32] = e
        for j in range(i,i+span):
            b[32+j//4] &= ~(1 << ((j%4)*2))
    put(0,0,1,'wifi',b'\x01')
    payload=b'http://old.example/ota/\0'
    put(1,1,0x21,'ota_url',struct.pack('<HHI',len(payload),0xffff,zlib.crc32(payload,0xffffffff)),2)
    b[128:128+len(payload)] = payload
    put(3,1,0x14,'force_ap',struct.pack('<i',1))
    return bytes(b)


def test_patch_retains_all_unrelated_entries_and_page_metadata():
    original=fixture()
    result, changed=patch_existing(original, {('wifi','ota_url'):'http://pc/ota/',('wifi','force_ap'):0})
    assert result[:96] == original[:96]
    assert result[192:] == original[192:]
    assert b'http://pc/ota/\0' in result
    assert result[184:188] == bytes(4)
    assert set(changed) == {'wifi:ota_url','wifi:force_ap'}


def test_patch_rejects_growth_or_missing_keys_without_touching_original():
    original=fixture()
    with pytest.raises(ValueError,match='capacity'):
        patch_existing(original,{('wifi','ota_url'):'x'*80})
    with pytest.raises(ValueError,match='Missing'):
        patch_existing(original,{('wifi','missing'):0})


def test_corrupt_crc_is_rejected():
    original=bytearray(fixture()); original[104] ^= 1
    with pytest.raises(ValueError,match='CRC'):
        patch_existing(bytes(original),{('wifi','ota_url'):'http://pc/'})
