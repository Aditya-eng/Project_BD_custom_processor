"""GPS L1C ranging and overlay codes (IS-GPS-800J 3.2.2.1, 3.3; Tables 3.2-2, 3.2-3, 6.2-1).

- Legendre sequence L(t), t = 0..10222: L(0) = 0, L(t) = 1 iff t is a quadratic residue mod 10223.
- Weil code W(t; w) = L(t) xor L((t + w) mod 10223).
- Ranging code (10230 chips): expansion 0110100 inserted before the p-th Weil chip.
- Overlay L1CO (1800 bits, one per 10 ms code period): s(k) = xor of s(k - j) for the
  polynomial coefficients m_j (j = 1..11), started from the table's initial 11 bits
  (first in time first). This convention reproduces every table's final 11 bits
  (checked by tools/import_is800.py and the tests).
- L1CP is TMBOC: chips with t mod 33 in {0, 4, 6, 29} (t counted from the start of each
  code period) are BOC(6,1), all others BOC(1,1). L1CD is BOC(1,1).
"""
from functools import lru_cache

import numpy as np

L1C_N = 10223
L1C_LEN = 10230
L1C_CHIP_RATE = 1.023e6
L1C_FREQ = 1575.42e6
EXPANSION = (0, 1, 1, 0, 1, 0, 0)
OVERLAY_LEN = 1800
TMBOC_BOC61 = (0, 4, 6, 29)


@lru_cache(maxsize=None)
def legendre() -> np.ndarray:
    seq = np.zeros(L1C_N, dtype=np.uint8)
    seq[(np.arange(1, L1C_N, dtype=np.int64) ** 2) % L1C_N] = 1
    seq[0] = 0
    return seq


def weil_code(w: int, p: int) -> np.ndarray:
    L = legendre()
    wc = L ^ np.roll(L, -w)                     # L(t) xor L(t + w)
    return np.concatenate([wc[:p - 1], np.array(EXPANSION, dtype=np.uint8), wc[p - 1:]])


def l1c_code(prn: int, component: str = "P") -> np.ndarray:
    """10230-chip L1CP ('P') or L1CD ('D') ranging code (logic 0/1)."""
    from .tables.gps_l1c_table import L1C_CODES
    w, p = L1C_CODES[prn][component][:2]
    return weil_code(w, p)


def overlay_bits(poly: int, init: str, n: int = OVERLAY_LEN) -> list:
    m = [(poly >> j) & 1 for j in range(12)]
    s = [int(c) for c in init]
    while len(s) < n:
        k = len(s)
        v = 0
        for j in range(1, 12):
            if m[j]:
                v ^= s[k - j]
        s.append(v)
    return s[:n]


def l1co_overlay(prn: int) -> tuple:
    from .tables.gps_l1c_table import L1CO
    poly, init, _ = L1CO[prn]
    return tuple(overlay_bits(poly, init))


def tmboc_mask() -> np.ndarray:
    """True for L1CP chips that are BOC(6,1) symbols."""
    return np.isin(np.arange(L1C_LEN) % 33, TMBOC_BOC61)
