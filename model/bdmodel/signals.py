"""Signal definitions shared by acquisition, tracking and simulation.

A SignalSpec says everything the receiver chain needs about one signal
component: its primary code, chip rate, carrier, subcarrier, secondary
(overlay) code and whether it carries data.
"""
from dataclasses import dataclass, replace
from functools import lru_cache
from typing import Callable, Optional

import numpy as np

from . import bds_b1c as b1c
from . import bds_b1i as b1i
from . import bds_b2a as b2a
from . import galileo as gal
from . import glonass as glo
from . import navic
from . import gps_l1c as l1c
from . import gps_l2c as l2c
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
    qmboc: bool = False                       # simulation only: BDS B1C pilot QMBOC(6,1,4/33)
    tdm_slot: Optional[int] = None            # chip-by-chip time multiplex: the half chip (0/1) this
                                              # code occupies; the replica is zero in the other half

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

# GPS L2C (IS-GPS-200N): CM (data) and CL (pilot) alternate every half chip, CM first.
GPS_L2CM = SignalSpec("GPS L2 CM", lambda p: l2c.l2c_code(p, "M"), l2c.CM_LEN, l2c.L2C_CHIP_RATE,
                      l2c.L2_FREQ, tdm_slot=0)
GPS_L2CL = SignalSpec("GPS L2 CL", lambda p: l2c.l2c_code(p, "L"), l2c.CL_LEN, l2c.L2C_CHIP_RATE,
                      l2c.L2_FREQ, tdm_slot=1, pilot=True)

# SBAS L1 (PRN 120-158): C/A codes from IS-GPS-200N Table 6-I; 500 sps = 2 epochs/symbol
# (see sbas.py). Data is not a secondary code, so the spec is the plain C/A one.
SBAS_L1 = SignalSpec("SBAS L1", ca_code, CA_LEN, CA_CHIP_RATE, L1_FREQ)

# QZSS (PRN 193-202) on the GPS signal designs; codes from the GPS ICDs' additional
# tables (see qzss.py). Separate names keep separate code caches and readable logs.
QZSS_L1CA = replace(GPS_L1CA, name="QZSS L1 C/A")
QZSS_L1CP = replace(GPS_L1CP, name="QZSS L1CP")
QZSS_L1CD = replace(GPS_L1CD, name="QZSS L1CD")
QZSS_L2CM = replace(GPS_L2CM, name="QZSS L2 CM")
QZSS_L2CL = replace(GPS_L2CL, name="QZSS L2 CL")
QZSS_L5I = replace(GPS_L5I, name="QZSS L5-I")
QZSS_L5Q = replace(GPS_L5Q, name="QZSS L5-Q")

# NavIC L5 SPS (ISRO-IRNSS-ICD-SPS-1.1): BPSK(1), 50 sps = 20 epochs/symbol. The code
# table is generated locally from the user's copy of the ICD (navic.py).
NAVIC_L5 = SignalSpec("NavIC L5 SPS", navic.l5_code, navic.NAVIC_LEN, navic.NAVIC_CHIP_RATE,
                      navic.NAVIC_L5_FREQ)

# BeiDou B1I (BDS-SIS-ICD-B1I-3.0): NH20 on MEO/IGSO (D1, 50 bps); GEO (D2, 500 bps) has none.
BDS_B1I = SignalSpec("BDS B1I", b1i.b1i_code, b1i.B1I_LEN, b1i.B1I_CHIP_RATE, b1i.B1I_FREQ,
                     secondary_fn=b1i.b1i_secondary)

# BeiDou B1C (BDS-SIS-ICD-B1C-1.0): data BOC(1,1) 100 sps in phase (1/4 of the power);
# pilot QMBOC(6,1,4/33) (3/4), tracked with a BOC(1,1) replica in quadrature.
BDS_B1C_D = SignalSpec("BDS B1C data", lambda p: b1c.b1c_code(p, "D"), b1c.B1C_LEN,
                       b1c.B1C_CHIP_RATE, b1c.B1C_FREQ, boc11=True)
BDS_B1C_P = SignalSpec("BDS B1C pilot", lambda p: b1c.b1c_code(p, "P"), b1c.B1C_LEN,
                       b1c.B1C_CHIP_RATE, b1c.B1C_FREQ, boc11=True, qmboc=True, pilot=True,
                       secondary_fn=b1c.pilot_secondary)

# BeiDou B2a (BDS-SIS-ICD-B2a-1.0): data (200 sps, 5-bit 00010) in phase, pilot in quadrature.
BDS_B2A_D = SignalSpec("BDS B2a data", lambda p: b2a.b2a_code(p, "D"), b2a.B2A_LEN,
                       b2a.B2A_CHIP_RATE, b2a.B2A_FREQ, secondary_fn=b2a.data_secondary)
BDS_B2A_P = SignalSpec("BDS B2a pilot", lambda p: b2a.b2a_code(p, "P"), b2a.B2A_LEN,
                       b2a.B2A_CHIP_RATE, b2a.B2A_FREQ, pilot=True,
                       secondary_fn=b2a.pilot_secondary)

# Galileo (OS SIS ICD). E1 is broadcast as CBOC(6,1,1/11) and tracked with a BOC(1,1) replica.
GAL_E1B = SignalSpec("Galileo E1-B", lambda p: gal.e1_code(p, "B"), gal.E1_LEN, gal.E1_CHIP_RATE,
                     gal.E1_FREQ, boc11=True, cboc="+")
GAL_E1C = SignalSpec("Galileo E1-C", lambda p: gal.e1_code(p, "C"), gal.E1_LEN, gal.E1_CHIP_RATE,
                     gal.E1_FREQ, boc11=True, cboc="-", pilot=True, secondary_fn=gal.e1c_secondary)
GAL_E5AI = SignalSpec("Galileo E5a-I", lambda p: gal.e5_code(p, "aI"), gal.E5_LEN,
                      gal.E5_CHIP_RATE, gal.E5A_FREQ, secondary_fn=gal.e5ai_secondary)
GAL_E5AQ = SignalSpec("Galileo E5a-Q", lambda p: gal.e5_code(p, "aQ"), gal.E5_LEN,
                      gal.E5_CHIP_RATE, gal.E5A_FREQ, pilot=True, secondary_fn=gal.e5aq_secondary)
GAL_E5BI = SignalSpec("Galileo E5b-I", lambda p: gal.e5_code(p, "bI"), gal.E5_LEN,
                      gal.E5_CHIP_RATE, gal.E5B_FREQ, secondary_fn=gal.e5bi_secondary)
GAL_E5BQ = SignalSpec("Galileo E5b-Q", lambda p: gal.e5_code(p, "bQ"), gal.E5_LEN,
                      gal.E5_CHIP_RATE, gal.E5B_FREQ, pilot=True, secondary_fn=gal.e5bq_secondary)


@lru_cache(maxsize=None)
def glonass_g1(k: int) -> SignalSpec:
    """GLONASS G1 on frequency number k: one shared ranging code, carrier 1602 + 0.5625 k MHz.
    The PRN argument of code() is ignored (FDMA)."""
    return SignalSpec(f"GLONASS G1 k={k:+d}", lambda prn: glo.ranging_code(), glo.CODE_LEN,
                      glo.CHIP_RATE, glo.carrier_hz(k))


def replica(spec: SignalSpec, prn: int, n: int, fs_hz: float, chip0: float = 0.0) -> np.ndarray:
    """Sampled replica (code, BOC subcarrier, TDM gate) starting at chip phase chip0:
    +/-1, or 0 in the half chips a time-multiplexed code does not occupy."""
    chips = chip0 + np.arange(n) * spec.chip_rate / fs_hz
    c = 1.0 - 2.0 * spec.code(prn)[np.floor(chips).astype(np.int64) % spec.code_len]
    if spec.boc11:
        c = c * np.where((chips % 1.0) < 0.5, 1.0, -1.0)
    if spec.tdm_slot is not None:
        c = c * (((chips % 1.0) >= 0.5) == spec.tdm_slot)
    return c


def secondary_sync(prompt_i, spec: SignalSpec, start=0, prn=None):
    """Align the secondary code with prompt epochs (sign-ambiguous, e.g. Costas).

    Returns the offset k such that epoch n carries secondary bit (n + k) % len,
    or None if the match is not unanimous.

    Each whole secondary period is scored on its own and the magnitudes averaged,
    so data bits aligned with the secondary period (GPS L5-I, Galileo E5a-I,
    BeiDou D1) may flip the sign from one period to the next.
    """
    code = spec.secondary_code(prn)
    if code is None:
        return 0
    sec = 1 - 2 * np.array(code)
    s = np.sign(np.asarray(prompt_i[start:], dtype=np.float64))
    L = len(sec)
    if len(s) < 2 * L:
        return None
    best = None
    for k in range(L):
        j = (-k) % L                      # first epoch of a secondary period
        n = (len(s) - j) // L             # >= 1 whole period, since len(s) >= 2L
        rows = s[j:j + n * L].reshape(n, L)
        score = np.mean(np.abs(rows @ sec)) / L
        if best is None or score > best[0]:
            best = (score, k)
    if best[0] < 0.95:
        return None
    return (best[1] - start) % L
