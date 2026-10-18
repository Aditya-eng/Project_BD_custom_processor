"""Synthetic real-IF GPS L1 C/A sample generator with 2-bit quantization.

Known truth (code phase, Doppler, carrier phase, nav bits) comes out with the
samples so tracking and observables can be checked against it, not against
another receiver.
"""
from dataclasses import dataclass

import numpy as np

from .gps_ca import CA_CHIP_RATE, CA_LEN, L1_FREQ, ca_code


@dataclass
class SatSignal:
    prn: int
    cn0_dbhz: float
    doppler_hz: float
    code_phase_chips: float     # code phase at t = 0
    carrier_phase_cycles: float = 0.0
    doppler_rate_hz_s: float = 0.0
    nav_bits: np.ndarray = None  # +/-1 per 20 ms, starting at the first code epoch

    def first_epoch_chips(self) -> float:
        """Unwrapped code phase of the code epoch that contains t = 0.

        Nav bit boundaries are aligned with code epochs from this point on.
        """
        return np.floor(self.code_phase_chips / CA_LEN) * CA_LEN


@dataclass
class FrontEnd:
    fs_hz: float = 16.368e6
    f_if_hz: float = 4.092e6
    adc_bits: int = 2            # 2 -> sign/magnitude {-3,-1,+1,+3}
    threshold_sigma: float = 1.0


def _quantize(x: np.ndarray, fe: FrontEnd) -> np.ndarray:
    if fe.adc_bits == 2:
        mag = np.where(np.abs(x) >= fe.threshold_sigma, 3, 1)
        return (np.where(x >= 0, 1, -1) * mag).astype(np.int8)
    levels = 1 << (fe.adc_bits - 1)
    q = np.clip(np.floor(x * levels / 3.0), -levels, levels - 1)
    return q.astype(np.int8)


def code_chips_at(sat: SatSignal, t: np.ndarray) -> np.ndarray:
    """Received code phase in chips (unwrapped) at time t."""
    f0 = sat.doppler_hz
    fd_int = f0 * t + 0.5 * sat.doppler_rate_hz_s * t * t
    return sat.code_phase_chips + CA_CHIP_RATE * t + fd_int * (CA_CHIP_RATE / L1_FREQ)


def generate(sats, fe: FrontEnd, duration_s: float, seed: int = 1, chunk: int = 1 << 20):
    """Return int8 quantized samples (noise sigma = 1 before quantization)."""
    rng = np.random.default_rng(seed)
    n_total = int(round(duration_s * fe.fs_hz))
    out = np.empty(n_total, dtype=np.int8)
    codes = {s.prn: 1.0 - 2.0 * ca_code(s.prn) for s in sats}
    for start in range(0, n_total, chunk):
        n = np.arange(start, min(start + chunk, n_total))
        t = n / fe.fs_hz
        x = rng.standard_normal(len(n))
        for s in sats:
            amp = 2.0 * np.sqrt(10 ** (s.cn0_dbhz / 10) / fe.fs_hz)
            chips = code_chips_at(s, t)
            code = codes[s.prn][np.floor(chips).astype(np.int64) % CA_LEN]
            if s.nav_bits is not None:
                bit_idx = np.floor((chips - s.first_epoch_chips()) / (20 * CA_LEN)).astype(np.int64)
                code = code * s.nav_bits[np.clip(bit_idx, 0, len(s.nav_bits) - 1)]
            phase = (fe.f_if_hz + s.doppler_hz) * t + 0.5 * s.doppler_rate_hz_s * t * t
            x += amp * code * np.cos(2 * np.pi * (phase + s.carrier_phase_cycles))
        out[start:start + len(n)] = _quantize(x, fe)
    return out

