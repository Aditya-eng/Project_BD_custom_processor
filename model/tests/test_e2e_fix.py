"""T1.6: IF samples -> acquisition -> tracking -> LNAV sync -> PVT, against truth.

Ephemerides are taken from the scenario (decoding subframes 1-3 needs 18+ s of
signal); time comes from the HOW decoded off the simulated signal itself.
"""
import numpy as np
import pytest

from bdmodel import pvt
from bdmodel.acquisition import acquire
from bdmodel.ephemeris import C
from bdmodel.navproc import nav_sync, sv_time_at
from bdmodel.scenario import Scenario
from bdmodel.tracking import Tracker


@pytest.fixture(scope="module")
def run():
    sc = Scenario.build()
    x = sc.generate(2.6)
    fs = sc.fe.fs_hz
    tic = int(2.5 * fs)
    eph = {s["prn"]: s["eph"] for s in sc.sats}
    found = [a for a in (acquire(x, p, fs, sc.fe.f_if_hz) for p in range(1, 33)) if a.detected]
    out = []
    for a in found:
        tr = Tracker(a.prn, fs, sc.fe.f_if_hz, a.doppler_hz, a.code_phase_chips, tic_samples=(tic,))
        tr.run(x)
        ns = nav_sync([r.ip for r in tr.records])
        if ns is not None and tr.meas and a.prn in eph:
            truth = sc.t_gps(tic) - sc.delay(eph[a.prn], np.array([tic / fs]))[0]
            out.append((a.prn, sv_time_at(tr.meas[0], ns), truth))
    return sc, found, out, tic


def test_acquisition_matches_sky(run):
    sc, found, _, _ = run
    assert {a.prn for a in found} == {s["prn"] for s in sc.sats}


def test_nav_sync_and_transmit_times(run):
    sc, _, out, _ = run
    assert len(out) == len(sc.sats)
    errs = np.array([(t - truth) * C for _, t, truth in out])
    assert np.max(np.abs(errs)) < 10.0          # metres; code noise at 40-46 dB-Hz


def test_position_and_time_fix(run):
    sc, _, out, tic = run
    eph = {s["prn"]: s["eph"] for s in sc.sats}
    sol = pvt.solve([t for _, t, _ in out], [eph[p] for p, _, _ in out])
    assert np.linalg.norm(sol.pos - sc.rx_ecef) < 15.0
    assert abs(sol.t_rx_gps - sc.t_gps(tic)) < 50e-9
