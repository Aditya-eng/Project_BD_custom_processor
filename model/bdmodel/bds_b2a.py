"""BeiDou B2a ranging codes (BDS-SIS-ICD-B2a-1.0, 4.2-4.3 and 5; Tables 5-2, 5-3, 5-4).

- Carrier 1176.45 MHz (same as GPS L5 / Galileo E5a). s = data + j*pilot: data on the
  in-phase carrier, pilot in quadrature, equal power; both BPSK(10), 10230-chip 1 ms
  primary codes. Logic 0 -> +1, 1 -> -1.
- Primary code: register 1 xor register 2, two 13-stage shift registers (Figures 5-2,
  5-3). Each clock shifts stage k into k+1 and loads stage 1 with the XOR of the
  polynomial's stages; the output is stage 13. Data: g1 = 1+x+x^5+x^11+x^13,
  g2 = 1+x^3+x^5+x^9+x^11+x^12+x^13. Pilot: g1 = 1+x^3+x^6+x^7+x^13,
  g2 = 1+x+x^5+x^7+x^8+x^12+x^13. Register 1 starts all ones and is reset after chip
  8190; register 2 starts at the PRN's value s2,1..s2,13 (left to right; data and
  pilot share it except PRN 61-63, see tools/import_bds_b2a.py). Of eight
  candidate conventions only this one reproduces the printed first/last 24 chips;
  tools/import_bds_b2a.py then checks all 126 codes that way.
- Secondary codes: data 00010 for every PRN (one bit per 1 ms epoch, 200 sps symbols =
  one 5-bit period each); pilot 100 chips per PRN, a Weil code of length 1021
  (Legendre sequence, phase difference w) cyclically truncated from point p.
"""
from functools import lru_cache

import numpy as np

from . import weil

B2A_FREQ = 1176.45e6
B2A_CHIP_RATE = 10.23e6
B2A_LEN = 10230
DATA_SECONDARY = (0, 0, 0, 1, 0)
DATA_EPOCHS_PER_SYMBOL = 5
WEIL_N = 1021
PILOT_SECONDARY_LEN = 100
POLY = {"D": ((1, 5, 11, 13), (3, 5, 9, 11, 12, 13)),
        "P": ((3, 6, 7, 13), (1, 5, 7, 8, 12, 13))}


def primary(component: str, init2: str, n: int = B2A_LEN) -> np.ndarray:
    """n chips (logic 0/1) of the data ('D') or pilot ('P') primary code."""
    t1, t2 = POLY[component]
    r1 = [1] * 13
    r2 = [int(c) for c in init2]
    out = np.empty(n, dtype=np.uint8)
    for k in range(n):
        if k == 8190:
            r1 = [1] * 13
        out[k] = r1[12] ^ r2[12]
        f1 = 0
        for t in t1:
            f1 ^= r1[t - 1]
        f2 = 0
        for t in t2:
            f2 ^= r2[t - 1]
        r1 = [f1] + r1[:12]
        r2 = [f2] + r2[:12]
    return out


def legendre(n: int = WEIL_N) -> np.ndarray:
    return weil.legendre(n)


def weil_truncated(w: int, p: int, n0: int = PILOT_SECONDARY_LEN, n: int = WEIL_N) -> tuple:
    """Pilot secondary code (eqs. 5-3..5-5): see bdmodel/weil.py."""
    return tuple(int(b) for b in weil.weil_truncated(w, p, n0, n))


@lru_cache(maxsize=None)
def _code(prn: int, component: str) -> np.ndarray:
    from .tables.bds_b2a_table import B2A_CODES
    c = primary(component, B2A_CODES[prn][component])
    c.flags.writeable = False
    return c


def b2a_code(prn: int, component: str = "D") -> np.ndarray:
    """10230-chip B2a data ('D') or pilot ('P') primary code, logic 0/1."""
    return _code(prn, component)


def data_secondary(prn: int) -> tuple:
    return DATA_SECONDARY


def pilot_secondary(prn: int) -> tuple:
    from .tables.bds_b2a_table import B2A_CODES
    w, p = B2A_CODES[prn]["S"]
    return weil_truncated(w, p)
