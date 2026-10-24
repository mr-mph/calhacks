"""Tiny QR code generator (byte mode, error correction L, versions 1-6) rendered as SVG. No dependencies."""
# Adapted minimal implementation; enough for a short URL like http://10.42.0.1:8080/
_EC_CODEWORDS = {1: 7, 2: 10, 3: 15, 4: 20, 5: 26, 6: 18}            # EC level L, per block
_BLOCKS = {1: 1, 2: 1, 3: 1, 4: 1, 5: 1, 6: 2}
_DATA_CODEWORDS = {1: 19, 2: 34, 3: 55, 4: 80, 5: 108, 6: 136}
_ALIGN = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34]}

_EXP = [0] * 512
_LOG = [0] * 256
_x = 1
for _i in range(255):
    _EXP[_i] = _x
    _LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def _rs_generator(n):
    g = [1]
    for i in range(n):
        g = _poly_mul(g, [1, _EXP[i]])
    return g


def _poly_mul(a, b):
    r = [0] * (len(a) + len(b) - 1)
    for i, x in enumerate(a):
        for j, y in enumerate(b):
            if x and y:
                r[i + j] ^= _EXP[_LOG[x] + _LOG[y]]
    return r


def _rs_encode(data, nsym):
    gen = _rs_generator(nsym)
    msg = list(data) + [0] * nsym
    for i in range(len(data)):
        c = msg[i]
        if c:
            for j in range(1, len(gen)):
                msg[i + j] ^= _EXP[_LOG[gen[j]] + _LOG[c]]
    return msg[len(data):]


def _bits(data, version):
    cap = _DATA_CODEWORDS[version]
    b = []
    def put(v, n):
        for i in range(n - 1, -1, -1):
            b.append((v >> i) & 1)
    put(0b0100, 4)
    put(len(data), 8)
    for c in data:
        put(c, 8)
    put(0, min(4, cap * 8 - len(b)))
    while len(b) % 8:
        b.append(0)
    pad = [0xEC, 0x11]
    i = 0
    while len(b) < cap * 8:
        put(pad[i % 2], 8)
        i += 1
    return [int("".join(map(str, b[i:i + 8])), 2) for i in range(0, len(b), 8)]


def _codewords(data, version):
    dcw = _bits(data, version)
    nb = _BLOCKS[version]
    ec = _EC_CODEWORDS[version]
    per = len(dcw) // nb
    blocks = [dcw[i * per:(i + 1) * per] for i in range(nb)]
    ecs = [_rs_encode(bl, ec) for bl in blocks]
    out = []
    for i in range(per):
        for bl in blocks:
            out.append(bl[i])
    for i in range(ec):
        for e in ecs:
            out.append(e[i])
    return out


def _matrix(version, cw):
    n = version * 4 + 17
    m = [[None] * n for _ in range(n)]
    def finder(r, c):
        for i in range(-1, 8):
            for j in range(-1, 8):
                rr, cc = r + i, c + j
                if 0 <= rr < n and 0 <= cc < n:
                    m[rr][cc] = 1 if (0 <= i <= 6 and j in (0, 6)) or (0 <= j <= 6 and i in (0, 6)) or (2 <= i <= 4 and 2 <= j <= 4) else 0
    finder(0, 0); finder(0, n - 7); finder(n - 7, 0)
    for i in range(8, n - 8):
        m[6][i] = m[i][6] = 1 if i % 2 == 0 else 0
    for a in _ALIGN[version]:
        for b in _ALIGN[version]:
            if m[a][b] is not None:
                continue
            for i in range(-2, 3):
                for j in range(-2, 3):
                    m[a + i][b + j] = 1 if max(abs(i), abs(j)) != 1 else 0
    for i in range(9):
        for (r, c) in ((8, i), (i, 8)):
            if m[r][c] is None:
                m[r][c] = 0
    for i in range(8):
        m[n - 1 - i][8] = m[8][n - 1 - i] = 0
    m[n - 8][8] = 1
    func = [[m[r][c] is not None for c in range(n)] for r in range(n)]
    bits = [(b >> (7 - i)) & 1 for b in cw for i in range(8)]
    bits += [0] * (n * n)
    k = 0
    c = n - 1
    up = True
    while c > 0:
        if c == 6:
            c -= 1
        rows = range(n - 1, -1, -1) if up else range(n)
        for r in rows:
            for cc in (c, c - 1):
                if m[r][cc] is None:
                    m[r][cc] = bits[k]
                    k += 1
        c -= 2
        up = not up
    # mask 0 (checkerboard) + format bits for EC L, mask 0
    for r in range(n):
        for cc in range(n):
            if not func[r][cc] and (r + cc) % 2 == 0:
                m[r][cc] ^= 1
    fmt = 0b111011111000100
    for i in range(15):
        bit = (fmt >> (14 - i)) & 1
        if i < 6:
            m[8][i] = bit
        elif i < 8:
            m[8][i + 1] = bit
        elif i == 8:
            m[7][8] = bit
        else:
            m[14 - i][8] = bit
        if i < 8:
            m[n - 1 - i][8] = bit
        else:
            m[8][n - 15 + i] = bit
    return m


def qr_matrix(text):
    data = text.encode("utf-8")
    for version in range(1, 7):
        if len(data) <= _DATA_CODEWORDS[version] - 2:
            break
    else:
        raise ValueError("text too long for this mini QR encoder")
    return _matrix(version, _codewords(data, version))


def qr_svg(text, scale=8, border=4):
    m = qr_matrix(text)
    n = len(m)
    size = (n + 2 * border) * scale
    rects = []
    for r in range(n):
        for c in range(n):
            if m[r][c]:
                rects.append('<rect x="%d" y="%d" width="%d" height="%d"/>' % ((c + border) * scale, (r + border) * scale, scale, scale))
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d">'
            '<rect width="100%%" height="100%%" fill="#fff"/><g fill="#000">%s</g></svg>') % (size, size, size, size, "".join(rects))
