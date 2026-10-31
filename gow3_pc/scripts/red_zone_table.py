#!/usr/bin/env python3
"""Writes <out>/red-zone.bin for the loader's --red-zone (src/red_zone.c): HEADER, then the
G3RZONE1 section of scripts/red_zone.py. A table that matches the image is kept.

Usage: red_zone_table.py out/boot-linked.bin --out out
Needs iced-x86: python -m pip install --no-cache-dir --target gow3_pc/out/pydeps iced-x86
"""
import argparse
import hashlib
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'out' / 'pydeps'))
from prepare import span, unpack
import red_zone

HEADER = struct.Struct('<8sQ32sQ')    # magic, image size, sha256, section bytes


def read_boot_linked(data):
    """Segments (address, size, flags) and image of a G3PROBE5 file, in link_modules.py's order."""
    magic, size, entry, ns, nr, ni, flags = unpack('<8s6Q', data, 0)
    if magic != b'G3PROBE5':
        raise ValueError('not a G3PROBE5 image')
    pos = 56 + 8 + 32   # header, procparam, main TLS
    nmodules, = unpack('<Q', data, pos)
    pos += 8 + nmodules * 56
    nbindings, = unpack('<Q', data, pos)
    pos += 8 + nbindings * 24
    segments = [unpack('<3Q', data, pos + i * 24) for i in range(ns)]
    pos += ns * 24 + ni * 128 + nr * 32
    return segments, span(data, pos, size)


def cached(path, digest, image_size):
    """Summary of a table that already matches, else None."""
    try:
        data = path.read_bytes()
        magic, size, sha, section_bytes = HEADER.unpack_from(data, 0)
        if magic != b'G3RZTAB1' or size != image_size or sha != digest or not section_bytes:
            return None
        section = data[HEADER.size:]
        magic, _, _, _, _, version, crc = red_zone.SECTION.unpack_from(section, 0)
        if magic != red_zone.MAGIC or version != red_zone.VERSION or crc != red_zone.source_crc():
            return None
        stats = dict(zip(red_zone.STATS_FIELDS, red_zone.STATS.unpack_from(section, red_zone.SECTION.size)))
        return red_zone.summary(stats) + ' (table kept)'
    except (OSError, struct.error, ValueError):
        return None


def main(argv):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('boot', type=Path)
    p.add_argument('--out', type=Path, default=Path(__file__).resolve().parent.parent / 'out')
    a = p.parse_args(argv)
    try:
        if red_zone.iced_x86 is None:
            raise RuntimeError('iced_x86 is not installed')
        segments, image = read_boot_linked(a.boot.read_bytes())
        digest = hashlib.sha256(image).digest()
        table = a.out / 'red-zone.bin'
        kept = cached(table, digest, len(image))
        if kept:
            print(kept)
            return 0
        builder, stats = red_zone.analyze(image, segments, red_zone.code_offset_for(len(image), 0))
        section = red_zone.encode_section(builder, stats)
        table.write_bytes(HEADER.pack(b'G3RZTAB1', len(image), digest, len(section)) + section)
    except (OSError, ValueError, RuntimeError) as e:
        print(f'Red zone: protection unavailable ({e})')
        return 1
    print(red_zone.summary(stats))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
