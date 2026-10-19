import numpy as np
import pytest

from bdmodel import pvt
from bdmodel.ephemeris import C, ecef_to_lla, lla_to_ecef, sat_clock, sat_position
from bdmodel.scenario import Scenario


def test_lla_roundtrip():
    p = lla_to_ecef(12.97, 77.59, 920.0)
    lat, lon, h = ecef_to_lla(p)
    assert abs(lat - 12.97) < 1e-9 and abs(lon - 77.59) < 1e-9 and abs(h - 920.0) < 1e-4


def test_orbits_are_physical():
    sc = Scenario.build()
    for s in sc.sats:
        e = s["eph"]
        r = np.linalg.norm(sat_position(e, 360000.0))
        a = e.sqrt_a ** 2
        assert a * (1 - e.e) - 1e3 < r < a * (1 + e.e) + 1e3       # on its Keplerian ellipse
        v = np.linalg.norm(sat_position(s["eph"], 360000.5) - sat_position(s["eph"], 359999.5))
        assert 2.5e3 < v < 4.0e3                                   # ECEF speed, m/s
        rel = sat_clock(s["eph"], 360000.0) - sat_clock(s["eph"].__class__(**{**s["eph"].__dict__, "e": 0.0}), 360000.0)
        assert abs(rel) < 50e-9                                    # relativistic term size
    assert len(sc.sats) >= 6


# Times are float64 TOW seconds: one ulp at 3.6e5 s is 5.8e-11 s (1.7 cm), which
# bounds the achievable consistency here. Observables move to split
# (integer ms, fraction) time in M4, before carrier phase is used.
def test_pvt_exact_on_noiseless_transmit_times():
    sc = Scenario.build()
    for t_rel in (0.0, 1.234):
        t_rx = sc.t_start_ms / 1000 + t_rel
        tsv = [t_rx - sc.delay(s["eph"], np.array([t_rel]))[0] for s in sc.sats]
        sol = pvt.solve(tsv, [s["eph"] for s in sc.sats])
        assert np.linalg.norm(sol.pos - sc.rx_ecef) < 0.05
        assert abs(sol.t_rx_gps - t_rx) < 2e-10
        assert np.max(np.abs(sol.residuals)) < 0.03
