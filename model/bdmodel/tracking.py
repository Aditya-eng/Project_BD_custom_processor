"""Host-side tracking loops driving the bit-exact correlator model.

In the v1 partition these loops run on the host PC. They see only what the
FPGA hands over (one dump per code epoch) and send back two control words,
so the same code drives the real hardware through sw/ later.
"""
import math
from collections import deque
from dataclasses import dataclass, field

import numpy as np

from .correlator import TrackChannel, freq_to_fcw, rate_to_fcw
from .gps_ca import CA_CHIP_RATE, CA_LEN, L1_FREQ, ca_code


@dataclass
class LoopConfig:
    pll_bw_hz: float = 15.0
    fll_bw_hz: float = 10.0
    fll_pullin_ms: int = 100       # FLL assist is switched off after this
    dll_bw_hz: float = 2.0
    half_spacing_chips: float = 0.5
    update_delay_epochs: int = 0   # 1 emulates a host that answers one epoch late


@dataclass
class EpochRecord:
    sample_index: int      # last sample of the epoch
    ip: int
    qp: int
    ie: int
    qe: int
    il: int
    ql: int
    carr_freq_hz: float
    code_rate_hz: float
    pll_err_cyc: float
    dll_err_chips: float


@dataclass
class Tracker:
    prn: int
    fs_hz: float
    f_if_hz: float
    doppler_hz: float
    code_phase_chips: float
    cfg: LoopConfig = field(default_factory=LoopConfig)
    tic_samples: tuple = ()        # absolute sample indices where the measurement latch fires

    def __post_init__(self):
        self.ch = TrackChannel(ca_code(self.prn))
        self.ch.half_spacing = int(round(self.cfg.half_spacing_chips * 2**32))
        cp = self.code_phase_chips % CA_LEN
        self.ch.load(carr_phase=0, code_frac=int((cp % 1) * 2**32), chip_idx=int(cp))
        self.carr_nco_hz = self.f_if_hz + self.doppler_hz
        self.code_nco_hz = CA_CHIP_RATE * (1 + self.doppler_hz / L1_FREQ)
        self._fll_int = self.doppler_hz
        self._apply(self.carr_nco_hz, self.code_nco_hz)
        self._pending = deque()
        self._prev_p = None
        self.records = []
        self.meas = []
        self.pos = 0

    def _apply(self, carr_hz, code_hz):
        self.ch.carr_fcw = freq_to_fcw(carr_hz, self.fs_hz)
        self.ch.code_fcw = rate_to_fcw(code_hz, self.fs_hz)

    def step(self, samples) -> bool:
        """Run one code epoch. Returns False when the samples run out."""
        m = self.ch.samples_to_epoch_end()
        if self.pos + m > len(samples):
            return False
        tics = [t - self.pos for t in self.tic_samples if self.pos <= t < self.pos + m]
        dumps, meas = self.ch.process(samples[self.pos:self.pos + m], tics)
        self.meas += meas
        self.pos += m
        assert len(dumps) == 1
        d = dumps[0]
        self._update(d)
        return True

    def run(self, samples):
        while self.step(samples):
            pass
        return self.records

    def _update(self, d):
        T = 1e-3
        cfg = self.cfg
        ip, qp = float(d.ip), float(d.qp)
        # Scalar libm math (not NumPy ufuncs) so the C++ twin in sw/ matches bit for bit.
        pll_err = math.atan(qp / ip) / (2 * math.pi) if ip != 0 else 0.0   # cycles, Costas

        fll_err = 0.0
        epoch_n = len(self.records)
        if self._prev_p is not None and epoch_n < cfg.fll_pullin_ms:
            pi, pq = self._prev_p
            dot = pi * ip + pq * qp
            cross = pi * qp - pq * ip
            if dot != 0:
                fll_err = math.atan(cross / dot) / (2 * math.pi * T)     # Hz
        self._prev_p = (ip, qp)

        w0p = cfg.pll_bw_hz / 0.53
        w0f = cfg.fll_bw_hz / 0.25 if epoch_n < cfg.fll_pullin_ms else 0.0
        self._fll_int += T * (w0p ** 2 * pll_err + w0f * fll_err)
        doppler = self._fll_int + 1.414 * w0p * pll_err
        carr_hz = self.f_if_hz + doppler

        e_mag = _mag(d.ie, d.qe)
        l_mag = _mag(d.il, d.ql)
        D = cfg.half_spacing_chips
        dll_err = (1 - D) * (e_mag - l_mag) / (e_mag + l_mag) if e_mag + l_mag else 0.0
        code_hz = CA_CHIP_RATE * (1 + doppler / L1_FREQ) + 4 * cfg.dll_bw_hz * dll_err

        self._pending.append((carr_hz, code_hz))
        if len(self._pending) > cfg.update_delay_epochs:
            self._apply(*self._pending.popleft())
        self.records.append(EpochRecord(d.sample_index, d.ip, d.qp, d.ie, d.qe, d.il, d.ql,
                                        carr_hz, code_hz, pll_err, dll_err))

    # --- Observables helpers -------------------------------------------------
    def replica_carrier_cycles(self) -> float:
        """Accumulated replica carrier phase (cycles) at the current sample."""
        return self.ch.carr_cycles + self.ch.carr_phase / 2**32

    def replica_code_chips(self) -> float:
        return self.ch.code_phase_chips()


def _mag(i, q):
    """|i + jq| as sqrt(i*i + q*q) in IEEE double; each step is correctly
    rounded, so C++ gets the identical result (math.hypot uses its own algorithm)."""
    fi, fq = float(i), float(q)
    return math.sqrt(fi * fi + fq * fq)


def bit_sync(ip_history, min_transitions=10, start=0):
    """Find the 20 ms bit boundary from prompt sign changes.

    Epochs before `start` (loop pull-in) are ignored. Returns the epoch
    offset (0..19) at which bits start, or None.
    """
    s = np.sign(np.asarray(ip_history, dtype=np.float64))
    trans = np.nonzero(s[1:] != s[:-1])[0] + 1
    trans = trans[trans >= start]
    if len(trans) < min_transitions:
        return None
    hist = np.bincount(trans % 20, minlength=20)
    best = int(np.argmax(hist))
    if hist[best] < 0.8 * len(trans):
        return None
    return best


def cn0_m2m4(ip, qp, T=1e-3):
    """Moment-method C/N0 estimate (dB-Hz) from prompt correlator outputs."""
    p = np.asarray(ip, dtype=np.float64) ** 2 + np.asarray(qp, dtype=np.float64) ** 2
    m2 = p.mean()
    m4 = (p ** 2).mean()
    pd = np.sqrt(max(2 * m2 ** 2 - m4, 0.0))
    pn = m2 - pd
    if pn <= 0:
        return float("inf")
    return 10 * np.log10(pd / (pn * T))
