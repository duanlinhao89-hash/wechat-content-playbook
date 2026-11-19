"""极简 PNG 裁剪器：纯标准库实现，仅支持 8bit RGB/RGBA 非隔行 PNG。"""
import sys, zlib, struct


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


def crop(src, dst, x, y, w, h):
    W, H, bpp, ctype, px = read_png(src)
    x = max(0, min(x, W - 1))
    y = max(0, min(y, H - 1))
    w = min(w, W - x)
    h = min(h, H - y)
    stride_src = W * bpp
    stride_dst = w * bpp
    out = bytearray(stride_dst * h)
    for j in range(h):
        s = (y + j) * stride_src + x * bpp
        out[j * stride_dst:(j + 1) * stride_dst] = px[s:s + stride_dst]
    write_png(dst, w, h, bpp, ctype, bytes(out))
    print('%s -> %dx%d' % (dst, w, h))


def crop_resize(src, dst, x, y, w, h, tw):
    """裁剪并按目标宽度做 box 平均缩放。"""
    W, H, bpp, ctype, px = read_png(src)
    x = max(0, min(x, W - 1))
    y = max(0, min(y, H - 1))
    w = min(w, W - x)
    h = min(h, H - y)
    th = max(1, int(round(h * tw / float(w))))
    def px_at(cx, cy):
        o = ((y + cy) * W + (x + cx)) * bpp
        return px[o:o + bpp]
    out = bytearray(tw * th * bpp)
    for j in range(th):
        y0 = int(j * h / th)
        y1 = max(y0 + 1, int((j + 1) * h / th))
        for i in range(tw):
            x0 = int(i * w / tw)
            x1 = max(x0 + 1, int((i + 1) * w / tw))
            acc = [0] * bpp
            n = 0
            for cy in range(y0, min(y1, h)):
                for cx in range(x0, min(x1, w)):
                    s = px_at(cx, cy)
                    for k in range(bpp):
                        acc[k] += s[k]
                    n += 1
            o = (j * tw + i) * bpp
            for k in range(bpp):
                out[o + k] = min(255, acc[k] // n)
    write_png(dst, tw, th, bpp, ctype, bytes(out))
    print('%s -> %dx%d' % (dst, tw, th))


if __name__ == '__main__':
    args = sys.argv[1:]
    if '--resize' in args:
        i = args.index('--resize')
        tw = int(args[i + 1])
        args = args[:i] + args[i + 2:]
        crop_resize(args[0], args[1], *[int(v) for v in args[2:6]], tw)
    else:
        crop(args[0], args[1], *[int(v) for v in args[2:6]])
