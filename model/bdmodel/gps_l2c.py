"""GPS L2C ranging codes (IS-GPS-200N 3.2.1.4-3.2.1.5, 3.3.2.4; Tables 3-IIa, 3-IIb, 6-II).

- L2 CM (10230 chips, 20 ms) and L2 CL (767250 chips, 1.5 s) both come from the same
  27-stage modular (Galois) shift register, polynomial 1112225171 (octal), clocked at
  511.5 kHz and reset to a per-PRN initial state every period.
- Register convention: the octal table value read as a 27-bit integer is the register
  state; each clock shifts right, and when the bit shifted out (bit 0) is 1 the state is
  XORed with the polynomial without its x^0 term, shifted down by one (0o445112474).
  The output chip is bit 0 of the state. With this convention, the state after
  (period - 1) clocks equals the table's "end shift register state" for every PRN and
  both codes (checked by tools/import_is200.py and the tests). Of six candidate
  conventions (shift direction, mask orientation, bit order), it is the only one that
  matches.
- The broadcast L2C chip stream is CM and CL time-multiplexed chip by chip at
  1.023 MHz. The text puts CM first ("the first L2 CM-code chip starts synchronously
  with the end/start of week epoch"; "alternating between L2 CM data and L2 CL chips"),
  so each 511.5 kHz chip period is [CM half, CL half]. Figure 3-12 is only schematic.
  If CM came second, every L2C pseudorange would be off by one 1.023 MHz slot
  (~293 m), so live-sky test T3.9 checks this against L1 C/A.
- CNAV symbols (50 sps, after rate-1/2 FEC) modulate CM, one symbol per CM period. CL
  is a data-free pilot.
"""
from functools import lru_cache

import numpy as np

L2_FREQ = 1227.60e6
L2C_CHIP_RATE = 511.5e3            # per component; the multiplexed stream runs at 1.023 MHz
CM_LEN = 10230
CL_LEN = 767250
POLY = 0o1112225171
MASK = POLY >> 1


def srg(state: int, n: int):
    """n output chips from `state`; returns (chips as uint8 array, state after n clocks)."""
    out = bytearray(n)
    s = state
    for k in range(n):
        o = s & 1
        out[k] = o
        s >>= 1
        if o:
            s ^= MASK
    return np.frombuffer(bytes(out), dtype=np.uint8), s


@lru_cache(maxsize=None)
def _code(prn: int, comp: str) -> np.ndarray:
    from .tables.gps_l2c_table import L2C_CODES
    cm_init, cl_init = L2C_CODES[prn][:2]
    if comp == "M":
        return srg(cm_init, CM_LEN)[0]
    if comp == "L":
        return srg(cl_init, CL_LEN)[0]
    raise ValueError(comp)


def l2c_code(prn: int, component: str = "M") -> np.ndarray:
    """L2 CM ('M', 10230 chips) or L2 CL ('L', 767250 chips) code, logic 0/1."""
    c = _code(prn, component)
    c.flags.writeable = False
    return c
