"""局部羽化压暗：给白字标题做可控遮罩，不整图压暗。

用法：
  python scrim.py 源.png 目标.png x0 y0 x1 y1 强度 羽化

x0 y0 x1 y1 为压暗矩形（可超出画布，让边缘落在画外），
强度 0-1（0.5 表示该区域亮度乘 0.5），羽化为渐变像素宽度。
"""
import sys
import zlib
import struct


def read_png(path):
    data = open(path, 'rb').read()
    assert data[:8] == b'\x89PNG\r\n\x1a\n', 'not a png'
    pos = 8
    idat = b''
    ihdr = None
    while pos < len(data):
        ln = struct.unpack('>I', data[pos:pos + 4])[0]
        typ = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + ln]
        if typ == b'IHDR':
            ihdr = struct.unpack('>IIBBBBB', body)
        elif typ == b'IDAT':
            idat += body
        elif typ == b'IEND':
            break
        pos += 12 + ln
    w, h, depth, ctype, comp, filt, inter = ihdr
    assert depth == 8 and inter == 0, 'unsupported png'
    bpp = {0: 1, 2: 3, 4: 2, 6: 4}[ctype]
    raw = zlib.decompress(idat)
    stride = w * bpp
    out = bytearray(stride * h)
    prev = bytearray(stride)
    p = 0
    for y in range(h):
        f = raw[p]
        p += 1
        line = bytearray(raw[p:p + stride])
        p += stride
        if f == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 0xFF
        elif f == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif f == 3:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xFF
        elif f == 4:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 0xFF
        out[y * stride:(y + 1) * stride] = line
        prev = line
    return w, h, bpp, ctype, bytes(out)


def write_png(path, w, h, bpp, ctype, pixels):
    stride = w * bpp
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        raw += pixels[y * stride:(y + 1) * stride]

    def chunk(typ, body):
        return (struct.pack('>I', len(body)) + typ + body +
                struct.pack('>I', zlib.crc32(typ + body) & 0xFFFFFFFF))

    ihdr = struct.pack('>IIBBBBB', w, h, 8, ctype, 0, 0, 0)
    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n')
        f.write(chunk(b'IHDR', ihdr))
        f.write(chunk(b'IDAT', zlib.compress(bytes(raw), 9)))
        f.write(chunk(b'IEND', b''))


def smooth(t):
    if t <= 0:
        return 0.0
    if t >= 1:
        return 1.0
    return t * t * (3 - 2 * t)


def main():
    a = sys.argv[1:]
    src, dst = a[0], a[1]
    x0, y0, x1, y1 = [int(v) for v in a[2:6]]
    strength = float(a[6])
    feather = max(1, int(a[7]))
    protect = int(a[8]) if len(a) > 8 else 0

    w, h, bpp, ctype, px = read_png(src)
    buf = bytearray(px)
    for y in range(h):
        if y < y0 or y >= y1:
            continue
        dy = min(y - y0, y1 - 1 - y)
        for x in range(w):
            if x < x0 or x >= x1:
                continue
            dx = min(x - x0, x1 - 1 - x)
            wt = smooth(min(dx, dy) / float(feather))
            if wt <= 0:
                continue
            o = (y * w + x) * bpp
            if protect and max(buf[o], buf[o + 1], buf[o + 2]) >= protect:
                continue
            k = 1.0 - strength * wt
            for c in range(3):
                buf[o + c] = int(buf[o + c] * k)
    write_png(dst, w, h, bpp, ctype, bytes(buf))
    print('%s -> %s  scrim %.2f feather %d protect>=%d' % (src, dst, strength, feather, protect))


if __name__ == '__main__':
    main()
