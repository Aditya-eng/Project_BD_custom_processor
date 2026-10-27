"""Real-IF simulator for any SignalSpec (code, BOC subcarrier, secondary code, data).

Each component is one signal component of one satellite on one carrier phase
(in-phase or quadrature), so multi-component signals such as GPS L5 (I5 data
+ Q5 pilot) are built from two components sharing Doppler and code phase.
"""
from dataclasses import dataclass
from typing import Optional

import numpy as np

from .signal_sim import FrontEnd, _quantize
from .signals import SignalSpec


@dataclass
class Component:
    spec: SignalSpec
    prn: int
    cn0_dbhz: float
    doppler_hz: float
    code_phase_chips: float            # at t = 0
    carrier_phase_cycles: float = 0.0
    quadrature: bool = False           # True: on -sin (Q), False: on cos (I)
    secondary_offset: int = 0          # secondary bit of the epoch containing t = 0
    data: Optional[np.ndarray] = None  # +/-1 symbols
    epochs_per_symbol: int = 1
    symbol_offset: int = 0             # epochs into the current symbol at t = 0

    def chips_at(self, t):
        rate = self.spec.chip_rate * (1 + self.doppler_hz / self.spec.carrier_hz)
        return self.code_phase_chips + rate * t


def generate(components, fe: FrontEnd, duration_s, seed=1, chunk=1 << 20):
    rng = np.random.default_rng(seed)
    n_total = int(round(duration_s * fe.fs_hz))
    out = np.empty(n_total, dtype=np.int8)
    for start in range(0, n_total, chunk):
        t = np.arange(start, min(start + chunk, n_total)) / fe.fs_hz
        x = rng.standard_normal(len(t))
        for c in components:
            spec = c.spec
            chips = c.chips_at(t)
            v = 1.0 - 2.0 * spec.code(c.prn)[np.floor(chips).astype(np.int64) % spec.code_len]
            frac = chips % 1.0
            sc1 = np.where(frac < 0.5, 1.0, -1.0)                 # sine BOC(1,1)
            if spec.cboc:
                # CBOC(6,1,1/11): alpha*BOC(1,1) +/- beta*BOC(6,1), 12 half-periods per chip
                sc6 = np.where(np.floor(frac * 12).astype(np.int64) % 2 == 0, 1.0, -1.0)
                a, b = np.sqrt(10 / 11), np.sqrt(1 / 11)
                v = v * (a * sc1 + (b if spec.cboc == "+" else -b) * sc6)
            elif spec.tmboc:
                # TMBOC(6,1,4/33): chips with index mod 33 in {0,4,6,29} carry BOC(6,1)
                sc6 = np.where(np.floor(frac * 12).astype(np.int64) % 2 == 0, 1.0, -1.0)
                idx = np.floor(chips).astype(np.int64) % spec.code_len
                v = v * np.where(np.isin(idx % 33, (0, 4, 6, 29)), sc6, sc1)
            elif spec.boc11:
                v = v * sc1
            if spec.tdm_slot is not None:
                # Each TDM component fills its half chips at the full amplitude, so a pair
                # (e.g. L2 CM + CL) is a constant envelope and cn0_dbhz is the pair's C/N0.
                v = v * ((frac >= 0.5) == spec.tdm_slot)
            epoch = (np.floor(chips / spec.code_len)
                     - np.floor(c.code_phase_chips / spec.code_len)).astype(np.int64)
            sec_code = spec.secondary_code(c.prn)
            if sec_code is not None:
                sec = 1.0 - 2.0 * np.array(sec_code)
                v = v * sec[(epoch + c.secondary_offset) % len(sec)]
            if c.data is not None:
                sym = (epoch + c.symbol_offset) // c.epochs_per_symbol
                v = v * c.data[np.clip(sym, 0, len(c.data) - 1)]
            amp = 2.0 * np.sqrt(10 ** (c.cn0_dbhz / 10) / fe.fs_hz)
            ph = 2 * np.pi * ((fe.f_if_hz + c.doppler_hz) * t + c.carrier_phase_cycles)
            x += amp * v * (-np.sin(ph) if c.quadrature else np.cos(ph))
        out[start:start + len(t)] = _quantize(x, fe)
    return out
