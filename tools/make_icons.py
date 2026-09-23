"""Draw the app icons: an optic-yellow ball with its seam, on the page's ink.

Pure standard library, like the rest of the project -- no Pillow. Sizes are
supersampled and averaged down, which is all the anti-aliasing a shape this
simple needs. Regenerate after changing the design:

    python3 tools/make_icons.py

Writes icons/icon-{size}.png. They are committed; the workflow copies them
next to the published page, and manifest.webmanifest points at them. The
design is full-bleed so it also works as a maskable icon: everything that
matters sits well inside the centre 80% that Android may crop to.
"""
import math
import os
import struct
import zlib

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "icons")

INK = (0x10, 0x16, 0x13)          # --ink, the page's near-black
BALL = (0xc3, 0xdc, 0x22)         # --ball, optic yellow
SIZES = [180, 192, 512]           # apple-touch-icon, and the two manifest sizes

SS = 4                            # supersampling factor per axis
BALL_R = 0.30                     # ball radius as a fraction of the icon
SEAM_W = 0.030                    # seam thickness, same units
SEAM_R = 1.30                     # seam arc radius, in ball radii
SEAM_C = 1.62                     # seam arc centre offset, in ball radii


def coverage(x, y, size):
    """How much of the sample at (x, y) is ball, and how much is seam (0..1).

    One sample point, so each returns 0 or 1; the averaging over SS*SS samples
    per pixel is what smooths the edges.
    """
    c = size / 2
    r = size * BALL_R
    dx, dy = x - c, y - c
    if math.hypot(dx, dy) > r:
        return 0.0, 0.0
    # Two arcs, each the edge of a big circle centred off to one side. Where
    # that edge crosses the ball, it draws the seam.
    for side in (-1, 1):
        d = math.hypot(dx - side * SEAM_C * r, dy)
        if abs(d - SEAM_R * r) <= size * SEAM_W / 2:
            return 1.0, 1.0
    return 1.0, 0.0


def render(size):
    """Rows of RGB bytes for one icon."""
    rows = []
    for py in range(size):
        row = bytearray()
        for px in range(size):
            ball = seam = 0.0
            for sy in range(SS):
                for sx in range(SS):
                    b, s = coverage(px + (sx + 0.5) / SS, py + (sy + 0.5) / SS, size)
                    ball += b
                    seam += s
            n = SS * SS
            ball, seam = ball / n, seam / n
            # Ink under the ball, ink again for the seam on top of it.
            for i in range(3):
                v = INK[i] * (1 - ball) + BALL[i] * ball
                row.append(round(v * (1 - seam) + INK[i] * seam))
        rows.append(bytes(row))
    return rows


def write_png(path, rows):
    size = len(rows)
    raw = b"".join(b"\x00" + r for r in rows)          # filter 0 on every row

    def chunk(tag, data):
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 9))
           + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)


def main():
    os.makedirs(OUT, exist_ok=True)
    for size in SIZES:
        path = os.path.join(OUT, f"icon-{size}.png")
        write_png(path, render(size))
        print(f"{path}  {os.path.getsize(path):,} bytes")


if __name__ == "__main__":
    main()
