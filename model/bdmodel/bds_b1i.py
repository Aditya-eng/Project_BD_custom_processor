"""BeiDou B1I ranging code and NH secondary code (BDS-SIS-ICD-B1I-3.0, 4.3, 5.2.1; Table 4-1).

- 2046 chips at 2.046 Mcps (1 ms), carrier 1561.098 MHz, BPSK.
- A balanced 2047-chip Gold code truncated by its last chip. G1 and G2 are 11-stage
  shift registers (Figure 4-1): each clock shifts stage k into k+1 and loads stage 1
  with the XOR of the feedback stages, G1 {1,7,8,9,10,11} (G1(X) = 1+X+X^7+X^8+X^9+
  X^10+X^11) and G2 {1,2,3,4,5,8,9,11} (G2(X) = 1+X+X^2+X^3+X^4+X^5+X^8+X^9+X^11).
  Both start at 01010101010 (stages 1..11; the pattern is a palindrome, so the bit
  order cannot be misread).
- Chip = G1 stage 11 XOR the G2 stages of the PRN's phase assignment (Table 4-1,
  two or three stages), taken before the shift.
- Every one of the 63 codes built this way is balanced (1024 ones in 2047 chips), as
  the ICD states; tools/import_bds_b1i.py and the tests check this, and deliberate
  convention errors break it for most PRNs.
- MEO/IGSO satellites: D1 message at 50 bps with the 20-bit NH code at 1 kbps, one NH
  bit per code period, aligned with the data bits. GEO satellites: D2 at 500 bps
  (2 code periods per bit), no NH code.
"""
from functools import lru_cache

import numpy as np

B1I_FREQ = 1561.098e6
B1I_CHIP_RATE = 2.046e6
B1I_LEN = 2046
G1_FEEDBACK = (1, 7, 8, 9, 10, 11)
G2_FEEDBACK = (1, 2, 3, 4, 5, 8, 9, 11)
INIT = "01010101010"
NH20 = (0, 0, 0, 0, 0, 1, 0, 0, 1, 1, 0, 1, 0, 1, 0, 0, 1, 1, 1, 0)
D1_EPOCHS_PER_BIT = 20
D2_EPOCHS_PER_BIT = 2


def gold(taps, n=2047) -> np.ndarray:
    """n chips of G1 xor (G2 stages `taps`), logic 0/1."""
    g1 = [None] + [int(c) for c in INIT]
    g2 = [None] + [int(c) for c in INIT]
    out = np.empty(n, dtype=np.uint8)
    for k in range(n):
        o = g1[11]
        for t in taps:
            o ^= g2[t]
        out[k] = o
        f1 = 0
        for t in G1_FEEDBACK:
            f1 ^= g1[t]
        f2 = 0
        for t in G2_FEEDBACK:
            f2 ^= g2[t]
        g1 = [None, f1] + g1[1:11]
        g2 = [None, f2] + g2[1:11]
    return out


@lru_cache(maxsize=None)
def _code(prn: int) -> np.ndarray:
    from .tables.bds_b1i_table import B1I_CODES
    c = gold(B1I_CODES[prn][1])[:B1I_LEN]
    c.flags.writeable = False
    return c


def b1i_code(prn: int) -> np.ndarray:
    """2046-chip B1I ranging code, logic 0/1."""
    return _code(prn)


def is_geo(prn: int) -> bool:
    from .tables.bds_b1i_table import B1I_CODES
    return B1I_CODES[prn][0] == "GEO"


def b1i_secondary(prn: int):
    """NH20 for MEO/IGSO (D1); None for GEO (D2)."""
    return None if is_geo(prn) else NH20


def epochs_per_bit(prn: int) -> int:
    return D2_EPOCHS_PER_BIT if is_geo(prn) else D1_EPOCHS_PER_BIT


def bit_phase(prompt_i, epochs_per_bit: int, start: int = 0) -> int:
    """Epoch offset k (0..epochs_per_bit-1) such that data bits start at epochs n with
    (n + k) % epochs_per_bit == 0: the alignment whose per-bit sums carry the most
    energy (sign flips inside a misaligned bit cancel). For D2 (2 ms bits, no NH code)."""
    ip = np.asarray(prompt_i[start:], dtype=np.float64)
    best = None
    for j in range(epochs_per_bit):
        m = (len(ip) - j) // epochs_per_bit
        e = np.abs(ip[j:j + m * epochs_per_bit].reshape(m, epochs_per_bit).sum(axis=1)).mean()
        if best is None or e > best[0]:
            best = (e, j)
    return (-(start + best[1])) % epochs_per_bit
