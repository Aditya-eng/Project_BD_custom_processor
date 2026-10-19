"""Single-epoch least-squares position/time solution from L1 C/A transmit times."""
from dataclasses import dataclass

import numpy as np

from .ephemeris import C, rotate_earth, sat_clock, sat_position


@dataclass
class PvtSolution:
    pos: np.ndarray          # ECEF, m
    clock_bias_s: float      # receiver clock minus GPS time at the measurement
    t_rx_gps: float          # GPS time of the measurement (TOW, s)
    residuals: np.ndarray    # m
    gdop: float
    n_sats: int


def solve(t_sv, ephs, t_rx_guess=None, x0=None, iters=10):
    """t_sv: SV transmit times (TOW, s) read from each tracked signal at one
    common receiver sample; ephs: matching ephemerides.

    The receiver's own time scale is t_rx_guess (default: latest transmit
    time + 75 ms); its offset from GPS time is solved as the clock bias.
    """
    t_sv = np.asarray(t_sv, dtype=np.float64)
    if t_rx_guess is None:
        t_rx_guess = t_sv.max() + 0.075
    dt_sv = np.array([sat_clock(e, t) for e, t in zip(ephs, t_sv)])
    t_tx = t_sv - dt_sv
    sat0 = np.array([sat_position(e, t) for e, t in zip(ephs, t_tx)])
    pr = C * (t_rx_guess - t_sv) + C * dt_sv     # pseudorange corrected for SV clock

    x = np.zeros(4) if x0 is None else np.concatenate([x0, [0.0]])
    for _ in range(iters):
        rho0 = np.linalg.norm(sat0 - x[:3], axis=1)
        sat = rotate_earth(sat0, rho0 / C)
        diff = sat - x[:3]
        rho = np.linalg.norm(diff, axis=1)
        h = np.hstack([-diff / rho[:, None], np.ones((len(rho), 1))])
        res = pr - (rho + x[3])
        dx, *_ = np.linalg.lstsq(h, res, rcond=None)
        x += dx
        if np.linalg.norm(dx[:3]) < 1e-4:
            break
    rho = np.linalg.norm(rotate_earth(sat0, np.linalg.norm(sat0 - x[:3], axis=1) / C) - x[:3], axis=1)
    res = pr - (rho + x[3])
    q = np.linalg.inv(h.T @ h)
    bias = x[3] / C
    return PvtSolution(x[:3].copy(), bias, t_rx_guess - bias, res, float(np.sqrt(np.trace(q))),
                       len(t_sv))
