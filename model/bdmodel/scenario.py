"""Geometry-driven GPS L1 C/A scenario: a synthetic constellation, a static
receiver at a known position, and the IF samples it would see.

Everything a receiver must recover is known exactly here: position, GPS time
of every sample, transmit times, Doppler. No atmosphere or multipath yet.
"""
from dataclasses import dataclass, field

import numpy as np

from .ephemeris import (C, Ephemeris, elevation_azimuth, lla_to_ecef, rotate_earth, sat_clock,
                        sat_position)
from .gps_ca import CA_CHIP_RATE, CA_LEN, L1_FREQ, ca_code
from .lnav import quantize, subframe_bits_for_tow
from .signal_sim import FrontEnd, _quantize


def make_constellation(week=2400, toe=360000.0, seed=0, n_planes=6, per_plane=4):
    """A 24-satellite Walker-like constellation with broadcast-resolution ephemerides."""
    rng = np.random.default_rng(seed)
    ephs = []
    prns = rng.permutation(np.arange(1, 33))[: n_planes * per_plane]
    for p in range(n_planes):
        for s in range(per_plane):
            prn = int(prns[p * per_plane + s])
            eph = Ephemeris(
                prn=prn, week=week, toc=toe, af0=float(rng.uniform(-3e-4, 3e-4)),
                af1=float(rng.uniform(-5e-12, 5e-12)), af2=0.0, tgd=float(rng.uniform(-1e-8, 0)),
                iodc=7, iode=7, toe=toe, sqrt_a=5153.6 + float(rng.uniform(-1, 1)),
                e=float(rng.uniform(0.001, 0.015)),
                m0=np.radians(90 * s + 15 * p + rng.uniform(-5, 5)),
                delta_n=4.5e-9, omega0=np.radians(60 * p + 10) - np.pi,
                i0=np.radians(55 + rng.uniform(-1, 1)), omega=np.radians(rng.uniform(-180, 180)),
                omega_dot=-8.0e-9, idot=1e-10, cuc=1e-6, cus=5e-6, crc=200.0, crs=20.0,
                cic=1e-8, cis=-1e-8)
            ephs.append(quantize(eph))
    return ephs


@dataclass
class Scenario:
    rx_ecef: np.ndarray
    t_start_ms: int             # GPS TOW of sample 0, integer milliseconds
    fe: FrontEnd
    ephs: list
    elev_mask_deg: float = 10.0
    sats: list = field(default_factory=list)   # visible: dicts with prn, eph, el, cn0

    @classmethod
    def build(cls, lat=12.97, lon=77.59, h=920.0, t_start_ms=359_999_200, fe=None, seed=0,
              elev_mask_deg=10.0):
        fe = fe or FrontEnd(fs_hz=4.0e6, f_if_hz=1.25e6)
        sc = cls(lla_to_ecef(lat, lon, h), t_start_ms, fe, make_constellation(seed=seed),
                 elev_mask_deg)
        t0 = t_start_ms / 1000.0
        for eph in sc.ephs:
            el, az = elevation_azimuth(sc.rx_ecef, sat_position(eph, t0))
            if el > elev_mask_deg:
                cn0 = 38.0 + 10.0 * np.sin(np.radians(el))
                sc.sats.append({"prn": eph.prn, "eph": eph, "el": float(el), "az": float(az),
                                "cn0": float(cn0)})
        return sc

    def t_gps(self, n):
        """GPS time (TOW, s) of sample n."""
        return self.t_start_ms / 1000.0 + np.asarray(n) / self.fe.fs_hz

    def delay(self, eph, t_rel):
        """tau = t_rx - t_sv (s) at receive times t_start + t_rel: geometric
        delay including Earth rotation, plus the SV clock offset."""
        t_rx = self.t_start_ms / 1000.0 + np.asarray(t_rel, dtype=np.float64)
        tau = np.full_like(t_rx, 0.075)
        for _ in range(4):
            sat = rotate_earth(sat_position(eph, t_rx - tau), tau)
            tau = np.linalg.norm(sat - self.rx_ecef, axis=-1) / C
        t_tx = t_rx - tau
        # SV time t_sv = t_tx + dt(t_sv); dt depends weakly on t, one pass is exact to < 1e-15 s
        dt = sat_clock(eph, t_tx)
        return tau - dt

    def generate(self, duration_s, seed=1, chunk=1 << 20):
        fe = self.fe
        rng = np.random.default_rng(seed)
        n_total = int(round(duration_s * fe.fs_hz))
        grid = np.arange(0, duration_s + 0.002, 1e-3)
        per_sat = []
        for s in self.sats:
            tau = self.delay(s["eph"], grid)
            bits = self._nav_bits(s["eph"], tau, duration_s)
            per_sat.append((s, tau, bits, 1.0 - 2.0 * ca_code(s["prn"])))
        out = np.empty(n_total, dtype=np.int8)
        for start in range(0, n_total, chunk):
            n = np.arange(start, min(start + chunk, n_total))
            t = n / fe.fs_hz
            x = rng.standard_normal(len(n))
            for s, tau_g, (bit0, bits), code in per_sat:
                tau = np.interp(t, grid, tau_g)
                t_sv_rel_ms = (t - tau) * 1000.0           # SV time minus t_start, ms
                chips = (t_sv_rel_ms * CA_CHIP_RATE / 1000.0) % CA_LEN
                c = code[chips.astype(np.int64)]
                bit_idx = np.floor((self.t_start_ms + t_sv_rel_ms) / 20.0).astype(np.int64) - bit0
                c = c * (1.0 - 2.0 * bits[bit_idx])
                phase = fe.f_if_hz * t - L1_FREQ * tau
                amp = 2.0 * np.sqrt(10 ** (s["cn0"] / 10) / fe.fs_hz)
                x += amp * c * np.cos(2 * np.pi * phase)
            out[start:start + len(n)] = _quantize(x, fe)
        return out

    def _nav_bits(self, eph, tau, duration_s):
        """LNAV bits covering the SV-time span of the run. Returns (first bit index, bits)."""
        t_sv_lo = self.t_start_ms - tau.max() * 1000 - 40
        t_sv_hi = self.t_start_ms + duration_s * 1000 + 40
        sf_lo = int(t_sv_lo // 6000)
        sf_hi = int(t_sv_hi // 6000)
        bits = []
        for k in range(sf_lo, sf_hi + 1):
            bits += subframe_bits_for_tow(6.0 * k, eph)
        return sf_lo * 300, np.array(bits, dtype=np.int64)

    def doppler(self, eph, t_rel):
        """L1 Doppler (Hz) at receive time t_start + t_rel."""
        d = 1e-3
        return -L1_FREQ * (self.delay(eph, t_rel + d) - self.delay(eph, t_rel - d)) / (2 * d)

