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
            coherent_ms=1, noncoherent=8, threshold=2.5, spec: SignalSpec = GPS_L1CA):
    spc = fs_hz * spec.epoch_s * coherent_ms   # samples per coherent block
    n = int(round(spc))
    need = n * noncoherent
    if len(samples) < need:
        raise ValueError("snapshot too short")
    x = np.asarray(samples[:need], dtype=np.float64).reshape(noncoherent, n)
    t = np.arange(n) / fs_hz

    code_fft_conj = np.conj(np.fft.fft(replica(spec, prn, n, fs_hz)))

    dopplers = np.arange(-doppler_max_hz, doppler_max_hz + doppler_step_hz / 2, doppler_step_hz)
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
