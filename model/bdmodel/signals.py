"""Signal definitions shared by acquisition, tracking and simulation.

A SignalSpec says everything the receiver chain needs about one signal
component: its primary code, chip rate, carrier, subcarrier, secondary
(overlay) code and whether it carries data.
"""
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable, Optional

import numpy as np

from . import galileo as gal
from . import gps_l1c as l1c
from .gps_ca import CA_CHIP_RATE, CA_LEN, L1_FREQ, ca_code
from .gps_l5 import L5_CHIP_RATE, L5_FREQ, L5_LEN, NH10, NH20, l5_code


@dataclass(frozen=True)
class SignalSpec:
    name: str
    code_fn: Callable[[int], np.ndarray]
    code_len: int
    chip_rate: float
    carrier_hz: float
    boc11: bool = False                       # sine-phased BOC(1,1) subcarrier on the replica
    secondary: Optional[tuple] = None         # overlay code bits, one per primary epoch
    pilot: bool = False                       # no data modulation
    secondary_fn: Optional[Callable[[int], tuple]] = None   # per-PRN overlay (overrides `secondary`)
    cboc: Optional[str] = None                # simulation only: '+'/'-' CBOC(6,1,1/11) as broadcast
    tmboc: bool = False                       # simulation only: GPS L1CP TMBOC(6,1,4/33) as broadcast

    def code(self, prn: int) -> np.ndarray:
        return _code_cached(self.name, prn, self.code_fn)

    def secondary_code(self, prn: int) -> Optional[tuple]:
        return self.secondary_fn(prn) if self.secondary_fn else self.secondary

    @property
    def epoch_s(self) -> float:
        return self.code_len / self.chip_rate


@lru_cache(maxsize=None)
def _code_cached(name, prn, fn):
    return fn(prn)


GPS_L1CA = SignalSpec("GPS L1 C/A", ca_code, CA_LEN, CA_CHIP_RATE, L1_FREQ)
GPS_L5I = SignalSpec("GPS L5-I", lambda p: l5_code(p, "I"), L5_LEN, L5_CHIP_RATE, L5_FREQ,
                     secondary=tuple(int(b) for b in NH10))
GPS_L5Q = SignalSpec("GPS L5-Q", lambda p: l5_code(p, "Q"), L5_LEN, L5_CHIP_RATE, L5_FREQ,
                     secondary=tuple(int(b) for b in NH20), pilot=True)

# GPS L1C (IS-GPS-800J): 10 ms codes; tracked with a BOC(1,1) replica.
GPS_L1CP = SignalSpec("GPS L1CP", lambda p: l1c.l1c_code(p, "P"), l1c.L1C_LEN, l1c.L1C_CHIP_RATE,
                      l1c.L1C_FREQ, boc11=True, tmboc=True, pilot=True,
                      secondary_fn=l1c.l1co_overlay)
GPS_L1CD = SignalSpec("GPS L1CD", lambda p: l1c.l1c_code(p, "D"), l1c.L1C_LEN, l1c.L1C_CHIP_RATE,
                      l1c.L1C_FREQ, boc11=True)

# Galileo (OS SIS ICD). E1 is broadcast as CBOC(6,1,1/11) and tracked with a BOC(1,1) replica.
GAL_E1B = SignalSpec("Galileo E1-B", lambda p: gal.e1_code(p, "B"), gal.E1_LEN, gal.E1_CHIP_RATE,
                     gal.E1_FREQ, boc11=True, cboc="+")
GAL_E1C = SignalSpec("Galileo E1-C", lambda p: gal.e1_code(p, "C"), gal.E1_LEN, gal.E1_CHIP_RATE,
                     gal.E1_FREQ, boc11=True, cboc="-", pilot=True, secondary_fn=gal.e1c_secondary)
GAL_E5AI = SignalSpec("Galileo E5a-I", lambda p: gal.e5_code(p, "aI"), gal.E5_LEN,
                      gal.E5_CHIP_RATE, gal.E5A_FREQ, secondary_fn=gal.e5ai_secondary)
GAL_E5AQ = SignalSpec("Galileo E5a-Q", lambda p: gal.e5_code(p, "aQ"), gal.E5_LEN,
                      gal.E5_CHIP_RATE, gal.E5A_FREQ, pilot=True, secondary_fn=gal.e5aq_secondary)


def replica(spec: SignalSpec, prn: int, n: int, fs_hz: float, chip0: float = 0.0) -> np.ndarray:
    """+/-1 sampled replica (code and BOC subcarrier) starting at chip phase chip0."""
    chips = chip0 + np.arange(n) * spec.chip_rate / fs_hz
    c = 1.0 - 2.0 * spec.code(prn)[np.floor(chips).astype(np.int64) % spec.code_len]
    if spec.boc11:
        c = c * np.where((chips % 1.0) < 0.5, 1.0, -1.0)
    return c


def secondary_sync(prompt_i, spec: SignalSpec, start=0, prn=None):
    """Align the secondary code with prompt epochs (sign-ambiguous, e.g. Costas).

    Returns the offset k such that epoch n carries secondary bit (n + k) % len,
    or None if the match is not unanimous.
    """
    code = spec.secondary_code(prn)
    if code is None:
        return 0
    sec = 1 - 2 * np.array(code)
    s = np.sign(np.asarray(prompt_i[start:], dtype=np.float64))
    L = len(sec)
    m = (len(s) // L) * L
    if m < 2 * L:
        return None
    s = s[:m]
    best = None
    for k in range(L):
        ref = np.tile(np.roll(sec, -k), m // L)
        score = abs(np.mean(s * ref))
        if best is None or score > best[0]:
            best = (score, k)
    if best[0] < 0.95:
        return None
    return (best[1] - start) % L
