"""Legendre sequences and truncated Weil codes (BDS-SIS-ICD-B1C-1.0 eqs. 5-1..5-3,
BDS-SIS-ICD-B2a-1.0 eqs. 5-3..5-5; the same construction as GPS L1C).

  L(k) = 1 if k != 0 is a quadratic residue mod N (N prime), else 0
  W(k; w) = L(k) xor L((k + w) mod N)
  c(n; w, p) = W((n + p - 1) mod N; w), n = 0 .. N0-1   (truncation point p is 1-based)
"""
from functools import lru_cache

import numpy as np


@lru_cache(maxsize=None)
def legendre(n: int) -> np.ndarray:
    seq = np.zeros(n, dtype=np.uint8)
    seq[(np.arange(1, n, dtype=np.int64) ** 2) % n] = 1
    seq[0] = 0
    seq.flags.writeable = False
    return seq


def weil_truncated(w: int, p: int, n0: int, n: int) -> np.ndarray:
    """N0 chips (logic 0/1) of the length-n Weil code with phase difference w, from point p."""
    L = legendre(n)
    idx = (np.arange(n0, dtype=np.int64) + p - 1) % n
    return L[idx] ^ L[(idx + w) % n]
