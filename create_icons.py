"""
Dev-only utility: generate PWA icon PNGs without Pillow.
Uses only Python builtins (struct + zlib).

Run once:  python create_icons.py
Commit the generated PNG files; this script can stay or be deleted.
"""
import struct
import zlib


def _make_icon_png(size: int, bg: tuple, fg: tuple, pad_ratio: float = 0.22) -> bytes:
    """
    Return PNG bytes for a simple icon:
      - solid bg_color background
      - fg_color rounded inner square (approximated with simple padding)
    No external dependencies required.
    """
    pad = max(1, int(size * pad_ratio))

    # Pre-build the two row types (bytes objects are fast to concatenate)
    bg_pixel = bytes(bg)
    fg_pixel = bytes(fg)

    bg_row = bg_pixel * size
    mid_row = bg_pixel * pad + fg_pixel * (size - 2 * pad) + bg_pixel * pad

    raw_rows = []
    for y in range(size):
        filter_byte = b'\x00'  # PNG filter: None
        if pad <= y < size - pad:
            raw_rows.append(filter_byte + mid_row)
        else:
            raw_rows.append(filter_byte + bg_row)

    raw = b''.join(raw_rows)
    compressed = zlib.compress(raw, 6)

    def png_chunk(tag: bytes, data: bytes) -> bytes:
        c = tag + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xFFFFFFFF)

    # Bit depth=8, colour type=2 (RGB), compression=0, filter=0, interlace=0
    ihdr_data = struct.pack('>IIBBBBB', size, size, 8, 2, 0, 0, 0)

    return (
        b'\x89PNG\r\n\x1a\n'
        + png_chunk(b'IHDR', ihdr_data)
        + png_chunk(b'IDAT', compressed)
        + png_chunk(b'IEND', b'')
    )


def create_icon(size: int, path: str) -> None:
    bg = (0x30, 0xB0, 0xC7)   # #30b0c7 — brand primary (teal)
    fg = (0xFF, 0xFF, 0xFF)    # white inner square
    data = _make_icon_png(size, bg, fg)
    with open(path, 'wb') as f:
        f.write(data)
    print(f'  ✓ {path}  ({size}×{size}, {len(data):,} bytes)')


if __name__ == '__main__':
    print('Generating PWA icons...')
    create_icon(192, 'static/icon-192.png')
    create_icon(512, 'static/icon-512.png')
    create_icon(180, 'static/apple-touch-icon.png')
    print('Done.')
