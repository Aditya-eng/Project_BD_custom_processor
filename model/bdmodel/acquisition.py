"""FFT parallel-code-phase acquisition (host software in the v1 partition)."""
from dataclasses import dataclass

import numpy as np

from .signals import GPS_L1CA, SignalSpec, replica


@dataclass
class AcqResult:
    prn: int
    detected: bool
    doppler_hz: float
    code_phase_chips: float   # replica chip phase at sample 0 of the snapshot
    code_phase_samples: int
    metric: float             # peak / second-highest peak outside +/-1 chip


def acquire(samples, prn, fs_hz, f_if_hz, doppler_max_hz=5000.0, doppler_step_hz=250.0,
            coherent_ms=1, noncoherent=8, threshold=2.5, spec: SignalSpec = GPS_L1CA,
            doppler_center_hz=0.0):
    """Search +/-doppler_max_hz around doppler_center_hz (aiding, e.g. from L1 C/A
    of the same satellite, narrows the search for long codes such as L1C)."""
    spc = fs_hz * spec.epoch_s * coherent_ms   # samples per coherent block
    n = int(round(spc))
    need = n * noncoherent
    if len(samples) < need:
        raise ValueError("snapshot too short")
    x = np.asarray(samples[:need], dtype=np.float64).reshape(noncoherent, n)
    t = np.arange(n) / fs_hz

    code_fft_conj = np.conj(np.fft.fft(replica(spec, prn, n, fs_hz)))

    dopplers = doppler_center_hz + np.arange(-doppler_max_hz, doppler_max_hz + doppler_step_hz / 2,
                                             doppler_step_hz)
    surface = np.zeros((len(dopplers), n))
    for di, fd in enumerate(dopplers):
        lo = np.exp(-2j * np.pi * (f_if_hz + fd) * t)
        for k in range(noncoherent):
            # Restart the LO phase at each block start time.
            phase0 = np.exp(-2j * np.pi * (f_if_hz + fd) * k * n / fs_hz)
            corr = np.fft.ifft(np.fft.fft(x[k] * lo * phase0) * code_fft_conj)
            surface[di] += np.abs(corr) ** 2

    di, si = np.unravel_index(np.argmax(surface), surface.shape)
    peak = surface[di, si]
    spc_chip = fs_hz / spec.chip_rate
    excl = int(np.ceil(spc_chip)) + 1
    row = surface[di].copy()
    idx = (np.arange(-excl, excl + 1) + si) % n
    row[idx] = 0
    metric = peak / row.max()
    # Correlation peak at lag `si` means the received code is delayed by si
    # samples: the replica must start at chip phase -si samples.
    code_phase = (-si * spec.chip_rate / fs_hz) % spec.code_len
    return AcqResult(prn, metric > threshold, float(dopplers[di]), code_phase, int(si), float(metric))


def refine_doppler(samples, acq: AcqResult, fs_hz, f_if_hz, spec: SignalSpec = GPS_L1CA,
                   span_hz=200.0, step_hz=5.0, blocks=8):
    """Fine Doppler search at the acquired code phase, on blocks aligned to code epochs.

    Coarse FFT blocks straddle epoch boundaries, so a data or secondary-code sign
    flip inside a block smears the Doppler estimate. Once the code phase is
    known, each block here covers exactly one primary code period (constant
    sign), and the per-block powers are summed non-coherently.
    """
    n = int(round(fs_hz * spec.epoch_s))
    # First epoch start: replica chip phase reaches a multiple of code_len.
    chips_to_epoch = (spec.code_len - acq.code_phase_chips) % spec.code_len
    start = int(np.ceil(chips_to_epoch * fs_hz / spec.chip_rate))
    need = start + blocks * n
    if len(samples) < need:
        raise ValueError("snapshot too short")
    chip0 = acq.code_phase_chips + start * spec.chip_rate / fs_hz
    rep = replica(spec, acq.prn, blocks * n, fs_hz, chip0)
    x = np.asarray(samples[start:need], dtype=np.float64) * rep
    t = (start + np.arange(blocks * n)) / fs_hz
    best = None
    for fd in np.arange(acq.doppler_hz - span_hz, acq.doppler_hz + span_hz + step_hz / 2, step_hz):
        y = (x * np.exp(-2j * np.pi * (f_if_hz + fd) * t)).reshape(blocks, n).sum(axis=1)
        p = np.sum(np.abs(y) ** 2)
        if best is None or p > best[0]:
            best = (p, fd)
    return AcqResult(acq.prn, acq.detected, float(best[1]), acq.code_phase_chips,
                     acq.code_phase_samples, acq.metric)
