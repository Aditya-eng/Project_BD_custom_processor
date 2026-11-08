"""BeiDou B1C ranging codes (BDS-SIS-ICD-B1C-1.0, 4.2 and 5; Tables 5-2, 5-3, 5-4).

- Carrier 1575.42 MHz, primary codes 10230 chips at 1.023 Mcps (10 ms), logic 0 -> +1.
- s = data + j*pilot (eq. 4-11):
    in phase:   1/2 * D * C_data * BOC(1,1)  +  sqrt(1/11) * C_pilot * BOC(6,1)
    quadrature: sqrt(29/44) * C_pilot * BOC(1,1)
  so the pilot is QMBOC(6,1,4/33): its BOC(6,1) part (4/33 of the pilot) sits in phase
  with the data. Power split data:pilot = 1:3. Data: 100 sps, one symbol per 10 ms
  primary period, no secondary code.
- Primary codes: Weil codes of length 10243 truncated to 10230 (w in 1..5121, truncation
  point p). Pilot secondary codes: Weil codes of length 3607 truncated to 1800 (one bit
  per primary period, 18 s), w in 1..1803. See bdmodel/weil.py.
- A BOC(1,1) replica on the pilot (quadrature) correlates with 29/33 of the pilot power:
  -0.56 dB, analytical.
"""
from functools import lru_cache

import numpy as np

from . import weil

B1C_FREQ = 1575.42e6
B1C_CHIP_RATE = 1.023e6
B1C_LEN = 10230
PRIMARY_N = 10243
SECONDARY_N = 3607
SECONDARY_LEN = 1800


@lru_cache(maxsize=None)
def _code(prn: int, component: str) -> np.ndarray:
    from .tables.bds_b1c_table import B1C_CODES
    w, p = B1C_CODES[prn][component]
    c = weil.weil_truncated(w, p, B1C_LEN, PRIMARY_N)
    c.flags.writeable = False
    return c


def b1c_code(prn: int, component: str = "D") -> np.ndarray:
    """10230-chip B1C data ('D') or pilot ('P') primary code, logic 0/1."""
    return _code(prn, component)


@lru_cache(maxsize=None)
def pilot_secondary(prn: int) -> tuple:
    from .tables.bds_b1c_table import B1C_CODES
    w, p = B1C_CODES[prn]["S"]
    return tuple(int(b) for b in weil.weil_truncated(w, p, SECONDARY_LEN, SECONDARY_N))
