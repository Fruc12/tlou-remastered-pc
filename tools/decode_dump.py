#!/usr/bin/env python3
"""Decode the renderer's raw image dumps (guest_<address>_<format>_NNN_WxH.raw) into PNG files.

Formats: Bc1 (RGBA unorm/sRGB), R8G8B8A8Unorm, R8G8Unorm, A2B10G10R10UnormPack32, and the HDR
R16G16B16A16Sfloat and B10G11R11UfloatPack32 (tone mapped for viewing: x / (1 + x), NaN magenta;
needs numpy). Usage: decode_dump.py <file.raw>...
"""
import re
import struct
import sys
from pathlib import Path

from PIL import Image


def rgb565(c):
    return ((c >> 11) & 31) * 255 // 31, ((c >> 5) & 63) * 255 // 63, (c & 31) * 255 // 31


def bc1(data, w, h):
    out = bytearray(w * h * 4)
    blocks_x = max(1, (w + 3) // 4)
    for by in range((h + 3) // 4):
        for bx in range(blocks_x):
            off = (by * blocks_x + bx) * 8
            if off + 8 > len(data):
                continue
            c0, c1, bits = struct.unpack_from("<HHI", data, off)
            a, b = rgb565(c0), rgb565(c1)
            if c0 > c1:
                pal = [a + (255,), b + (255,),
                       tuple((2 * x + y) // 3 for x, y in zip(a, b)) + (255,),
                       tuple((x + 2 * y) // 3 for x, y in zip(a, b)) + (255,)]
            else:
                pal = [a + (255,), b + (255,), tuple((x + y) // 2 for x, y in zip(a, b)) + (255,), (0, 0, 0, 0)]
            for i in range(16):
                x, y = bx * 4 + i % 4, by * 4 + i // 4
                if x < w and y < h:
                    p = (y * w + x) * 4
                    out[p:p + 4] = bytes(pal[(bits >> (2 * i)) & 3])
    return Image.frombytes("RGBA", (w, h), bytes(out))


def tone_mapped(rgb, w, h):
    """HDR values for viewing: x / (1 + x); NaN shows as magenta. Prints the statistics."""
    import numpy as np
    nan = np.isnan(rgb).any(axis=2)
    finite = np.where(np.isfinite(rgb), rgb, 0.0)
    print(f"  mean {finite.mean():.4g}, peak {finite.max():.4g}, NaN/inf pixels {int(nan.sum() + np.isinf(rgb).any(axis=2).sum())}")
    out = (np.clip(finite / (1 + finite), 0, 1) * 255).astype(np.uint8)
    out[nan] = (255, 0, 255)
    return Image.fromarray(out.reshape(h, w, 3), "RGB")


def half(data, w, h):
    import numpy as np
    values = np.frombuffer(data[:w * h * 8], dtype=np.float16).astype(np.float32).reshape(-1, 4)
    return tone_mapped(values[:, :3].reshape(h, w, 3), w, h)


def r11g11b10(data, w, h):
    """B10G11R11UfloatPack32: R bits 0-10 and G 11-21 (6-bit mantissa), B 22-31 (5-bit)."""
    import numpy as np
    packed = np.frombuffer(data[:w * h * 4], dtype=np.uint32)

    def small_float(bits, mantissa_bits):
        exponent = (bits >> mantissa_bits) & 31
        mantissa = (bits & ((1 << mantissa_bits) - 1)).astype(np.float32) / (1 << mantissa_bits)
        normal = (1 + mantissa) * np.exp2(exponent.astype(np.float32) - 15)
        value = np.where(exponent == 0, mantissa * np.exp2(-14.0), normal)
        return np.where(exponent == 31, np.inf, value).astype(np.float32)

    rgb = np.stack([small_float(packed & 0x7FF, 6), small_float((packed >> 11) & 0x7FF, 6),
                    small_float(packed >> 22, 5)], axis=1)
    return tone_mapped(rgb.reshape(h, w, 3), w, h)


def a2b10g10r10(data, w, h):
    import numpy as np
    packed = np.frombuffer(data[:w * h * 4], dtype=np.uint32)
    rgb = np.stack([packed & 1023, (packed >> 10) & 1023, (packed >> 20) & 1023], axis=1)
    return Image.fromarray((rgb * 255 // 1023).astype(np.uint8).reshape(h, w, 3), "RGB")


def main():
    for name in sys.argv[1:]:
        path = Path(name)
        # guest_<address>_<format>[_L<layer>|_M<level>]_<index>_<width>x<height>.raw
        m = re.search(r"_([A-Za-z0-9]+)(?:_[LM]\d+)?_\d+_(\d+)x(\d+)\.raw$", path.name)
        if not m:
            print(f"{path.name}: name not understood")
            continue
        fmt, w, h = m.group(1), int(m.group(2)), int(m.group(3))
        print(f"{path.name}:")
        data = path.read_bytes()
        if fmt.startswith("Bc1"):
            image = bc1(data, w, h)
        elif fmt == "R8G8B8A8Unorm":
            image = Image.frombytes("RGBA", (w, h), data[:w * h * 4])
        elif fmt == "R8G8Unorm":
            image = Image.frombytes("LA", (w, h), data[:w * h * 2]).convert("RGBA")
        elif fmt == "R16G16B16A16Sfloat":
            image = half(data, w, h)
        elif fmt == "B10G11R11UfloatPack32":
            image = r11g11b10(data, w, h)
        elif fmt == "A2B10G10R10UnormPack32":
            image = a2b10g10r10(data, w, h)
        else:
            print(f"{path.name}: format {fmt} not decoded")
            continue
        image.save(path.with_suffix(".png"))
        print(f"  -> {path.with_suffix('.png').name} ({fmt} {w}x{h})")


if __name__ == "__main__":
    main()
