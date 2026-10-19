"""GPS LNAV message (IS-GPS-200 20.3.2, 20.3.3, 20.3.5): parity, subframes 1-3, TLM/HOW.

Bits are lists/arrays of 0/1, bit 1 of a word first. Field layouts and scale
factors follow IS-GPS-200 Tables 20-I and 20-III. They are self-consistent
here (encode/decode round trip). Their match to live-sky data is checked
once recorded data is available (TEST_PLAN T2/T4).
"""
import numpy as np

from .ephemeris import GPS_PI, Ephemeris

PREAMBLE = [1, 0, 0, 0, 1, 0, 1, 1]
SUBFRAME_BITS = 300
WORD_BITS = 30

# Parity equations: (uses D29* (0) or D30* (1), 1-based data bit indices)
_PARITY = [
    (0, [1, 2, 3, 5, 6, 10, 11, 12, 13, 14, 17, 18, 20, 23]),
    (1, [2, 3, 4, 6, 7, 11, 12, 13, 14, 15, 18, 19, 21, 24]),
    (0, [1, 3, 4, 5, 7, 8, 12, 13, 14, 15, 16, 19, 20, 22]),
    (1, [2, 4, 5, 6, 8, 9, 13, 14, 15, 16, 17, 20, 21, 23]),
    (1, [1, 3, 5, 6, 7, 9, 10, 14, 15, 16, 17, 18, 21, 22, 24]),
    (0, [3, 5, 6, 8, 9, 10, 11, 13, 15, 19, 22, 23, 24]),
]


def parity(d, d29s, d30s):
    """Six parity bits D25..D30 for source data bits d[0..23]."""
    out = []
    for which, idx in _PARITY:
        p = d29s if which == 0 else d30s
        for i in idx:
            p ^= d[i - 1]
        out.append(p)
    return out


def encode_word(d, d29s, d30s):
    """Transmitted 30-bit word from 24 source bits and the previous word's D29*, D30*."""
    return [b ^ d30s for b in d] + parity(d, d29s, d30s)


def check_word(w, d29s, d30s):
    """Return (ok, source bits d1..d24) for a received 30-bit word."""
    d = [b ^ d30s for b in w[:24]]
    return parity(d, d29s, d30s) == list(w[24:30]), d


def _solve_t_bits(d, d29s, d30s):
    """Choose d23, d24 so that D29 = D30 = 0 (words 2 and 10)."""
    for t in ((0, 0), (0, 1), (1, 0), (1, 1)):
        dd = d[:22] + list(t)
        if parity(dd, d29s, d30s)[4:] == [0, 0]:
            return dd
    raise AssertionError("no t bits solution")


# ---- field packing ----
def _put(bits, start, nbits, value):
    """Place an integer (two's complement if negative) at 1-based bit `start`."""
    v = int(value) & ((1 << nbits) - 1)
    for k in range(nbits):
        bits[start - 1 + k] = (v >> (nbits - 1 - k)) & 1


def _get(bits, start, nbits, signed=False):
    v = 0
    for k in range(nbits):
        v = (v << 1) | int(bits[start - 1 + k])
    if signed and v & (1 << (nbits - 1)):
        v -= 1 << nbits
    return v


def _q(x, scale):
    return int(round(x / scale))


def _sc(rad):
    return rad / GPS_PI


# Data-field layout per subframe: list of (word, first bit, n bits, name, scale, signed, split)
# Fields split across words are given as (word, bit, n) for MSB part and LSB part.
def _fields(eph: Ephemeris):
    return {
        1: [
            ("week", [(3, 1, 10)], eph.week % 1024, False),
            ("ura", [(3, 13, 4)], eph.ura, False),
            ("health", [(3, 17, 6)], eph.health, False),
            ("iodc", [(3, 23, 2), (8, 1, 8)], eph.iodc, False),
            ("tgd", [(7, 17, 8)], _q(eph.tgd, 2.0 ** -31), True),
            ("toc", [(8, 9, 16)], _q(eph.toc, 2.0 ** 4), False),
            ("af2", [(9, 1, 8)], _q(eph.af2, 2.0 ** -55), True),
            ("af1", [(9, 9, 16)], _q(eph.af1, 2.0 ** -43), True),
            ("af0", [(10, 1, 22)], _q(eph.af0, 2.0 ** -31), True),
        ],
        2: [
            ("iode", [(3, 1, 8)], eph.iode, False),
            ("crs", [(3, 9, 16)], _q(eph.crs, 2.0 ** -5), True),
            ("delta_n", [(4, 1, 16)], _q(_sc(eph.delta_n), 2.0 ** -43), True),
            ("m0", [(4, 17, 8), (5, 1, 24)], _q(_sc(eph.m0), 2.0 ** -31), True),
            ("cuc", [(6, 1, 16)], _q(eph.cuc, 2.0 ** -29), True),
            ("e", [(6, 17, 8), (7, 1, 24)], _q(eph.e, 2.0 ** -33), False),
            ("cus", [(8, 1, 16)], _q(eph.cus, 2.0 ** -29), True),
            ("sqrt_a", [(8, 17, 8), (9, 1, 24)], _q(eph.sqrt_a, 2.0 ** -19), False),
            ("toe", [(10, 1, 16)], _q(eph.toe, 2.0 ** 4), False),
        ],
        3: [
            ("cic", [(3, 1, 16)], _q(eph.cic, 2.0 ** -29), True),
            ("omega0", [(3, 17, 8), (4, 1, 24)], _q(_sc(eph.omega0), 2.0 ** -31), True),
            ("cis", [(5, 1, 16)], _q(eph.cis, 2.0 ** -29), True),
            ("i0", [(5, 17, 8), (6, 1, 24)], _q(_sc(eph.i0), 2.0 ** -31), True),
            ("crc", [(7, 1, 16)], _q(eph.crc, 2.0 ** -5), True),
            ("omega", [(7, 17, 8), (8, 1, 24)], _q(_sc(eph.omega), 2.0 ** -31), True),
            ("omega_dot", [(9, 1, 24)], _q(_sc(eph.omega_dot), 2.0 ** -43), True),
            ("iode", [(10, 1, 8)], eph.iode, False),
            ("idot", [(10, 9, 14)], _q(_sc(eph.idot), 2.0 ** -43), True),
        ],
    }


_SCALE = {"tgd": 2.0 ** -31, "toc": 2.0 ** 4, "af2": 2.0 ** -55, "af1": 2.0 ** -43,
          "af0": 2.0 ** -31, "crs": 2.0 ** -5, "delta_n": 2.0 ** -43 * GPS_PI,
          "m0": 2.0 ** -31 * GPS_PI, "cuc": 2.0 ** -29, "e": 2.0 ** -33, "cus": 2.0 ** -29,
          "sqrt_a": 2.0 ** -19, "toe": 2.0 ** 4, "cic": 2.0 ** -29, "omega0": 2.0 ** -31 * GPS_PI,
          "cis": 2.0 ** -29, "i0": 2.0 ** -31 * GPS_PI, "crc": 2.0 ** -5,
          "omega": 2.0 ** -31 * GPS_PI, "omega_dot": 2.0 ** -43 * GPS_PI,
          "idot": 2.0 ** -43 * GPS_PI}


def _data_words(sf_id, eph):
    """24-bit source data for words 3..10 of subframe sf_id (index 0 = word 3)."""
    words = {w: [0] * 24 for w in range(3, 11)}
    if eph is not None and sf_id in (1, 2, 3):
        for _, parts, value, _signed in _fields(eph)[sf_id]:
            total = sum(p[2] for p in parts)
            v = int(value) & ((1 << total) - 1)
            shift = total
            for (w, b, n) in parts:
                shift -= n
                _put(words[w], b, n, (v >> shift) & ((1 << n) - 1))
    return [words[w] for w in range(3, 11)]


def encode_subframe(sf_id, tow_count_next, eph=None, alert=0, anti_spoof=0):
    """300 transmitted bits of one subframe. tow_count_next = HOW TOW count
    (start time of the NEXT subframe / 6 s). Subframes 4/5 carry zero data."""
    tlm = PREAMBLE + [0] * 14 + [0, 0]
    how = [0] * 24
    _put(how, 1, 17, tow_count_next)
    how[17] = alert
    how[18] = anti_spoof
    _put(how, 20, 3, sf_id)
    src = [tlm, how] + _data_words(sf_id, eph)
    out = []
    d29s, d30s = 0, 0
    for k, d in enumerate(src):
        if k in (1, 9):
            d = _solve_t_bits(d, d29s, d30s)
        w = encode_word(d, d29s, d30s)
        out += w
        d29s, d30s = w[28], w[29]
    return out


def subframe_bits_for_tow(tow_start, eph_for_prn):
    """Bits of the subframe that starts at GPS TOW `tow_start` (multiple of 6 s)."""
    k = int(round(tow_start / 6.0))
    sf_id = (k % 5) + 1
    return encode_subframe(sf_id, (k + 1) % 100800, eph_for_prn)


def decode_subframe(bits):
    """Check parity of all 10 words of a 300-bit subframe (D29*=D30*=0 before TLM).

    Returns dict with 'ok', 'tow_count', 'sf_id' and 'words' (source bits)."""
    d29s, d30s = 0, 0
    words = []
    ok = True
    for k in range(10):
        w = list(bits[30 * k: 30 * k + 30])
        good, d = check_word(w, d29s, d30s)
        ok &= good
        words.append(d)
        d29s, d30s = w[28], w[29]
    return {"ok": ok, "tow_count": _get(words[1], 1, 17), "sf_id": _get(words[1], 20, 3),
            "words": words}


def decode_tlm_how(bits):
    """Parity-check TLM and HOW only (first 60 bits). Returns (ok, tow_count, sf_id)."""
    ok1, d1 = check_word(list(bits[0:30]), 0, 0)
    ok2, d2 = check_word(list(bits[30:60]), bits[28], bits[29])
    ok = ok1 and ok2 and list(d1[:8]) == PREAMBLE
    return ok, _get(d2, 1, 17), _get(d2, 20, 3)


def ephemeris_from_subframes(sf1, sf2, sf3, prn) -> Ephemeris:
    """Build an Ephemeris from decoded subframes 1, 2, 3 (outputs of decode_subframe)."""
    vals = {}
    dummy = Ephemeris(prn, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    for sf_id, sf in ((1, sf1), (2, sf2), (3, sf3)):
        assert sf["ok"] and sf["sf_id"] == sf_id
        words = {w: sf["words"][w - 1] for w in range(3, 11)}
        for name, parts, _v, signed in _fields(dummy)[sf_id]:
            v = 0
            total = 0
            for (w, b, n) in parts:
                v = (v << n) | _get(words[w], b, n)
                total += n
            if signed and v & (1 << (total - 1)):
                v -= 1 << total
            vals[name] = v * _SCALE.get(name, 1)
    return Ephemeris(prn=prn, week=int(vals["week"]), toc=vals["toc"], af0=vals["af0"],
                     af1=vals["af1"], af2=vals["af2"], tgd=vals["tgd"], iodc=int(vals["iodc"]),
                     iode=int(vals["iode"]), toe=vals["toe"], sqrt_a=vals["sqrt_a"], e=vals["e"],
                     m0=vals["m0"], delta_n=vals["delta_n"], omega0=vals["omega0"], i0=vals["i0"],
                     omega=vals["omega"], omega_dot=vals["omega_dot"], idot=vals["idot"],
                     cuc=vals["cuc"], cus=vals["cus"], crc=vals["crc"], crs=vals["crs"],
                     cic=vals["cic"], cis=vals["cis"], health=int(vals["health"]),
                     ura=int(vals["ura"]))


def quantize(eph: Ephemeris) -> Ephemeris:
    """The ephemeris a receiver would decode (broadcast resolution)."""
    sfs = [decode_subframe(encode_subframe(k, 1, eph)) for k in (1, 2, 3)]
    q = ephemeris_from_subframes(*sfs, prn=eph.prn)
    q.week = eph.week
    return q


def find_subframe_start(bits):
    """Search a bit stream (0/1, unknown polarity) for TLM+HOW with valid parity.

    Returns (index, inverted, tow_count, sf_id) for the first hit, or None.
    """
    b = np.asarray(bits, dtype=np.int64)
    pre = np.array(PREAMBLE)
    for i in range(0, len(b) - 60 + 1):
        for inv in (0, 1):
            seg = b[i:i + 60] ^ inv
            if np.array_equal(seg[:8], pre):
                ok, tow, sf = decode_tlm_how(list(seg))
                if ok and 1 <= sf <= 5:
                    return i, bool(inv), tow, sf
    return None
