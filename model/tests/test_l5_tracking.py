"""GPS L5: acquire and track the Q5 pilot of a simulated I5 + Q5 signal, sync NH20."""
import numpy as np
import pytest

from bdmodel.acquisition import acquire
from bdmodel.signal_sim import FrontEnd
from bdmodel.signals import GPS_L5I, GPS_L5Q, secondary_sync
from bdmodel.sim_generic import Component, generate
from bdmodel.tracking import Tracker, cn0_m2m4

FE = FrontEnd(fs_hz=50e6, f_if_hz=13.0e6)   # real IF must hold the 20.46 MHz main lobe
SETTLE = 300


@pytest.fixture(scope="module")
def l5():
    rng = np.random.default_rng(4)
    q = Component(GPS_L5Q, 7, 45.0, -2345.6, 4321.25, 0.1, quadrature=True, secondary_offset=13)
    i = Component(GPS_L5I, 7, 45.0, -2345.6, 4321.25, 0.1, secondary_offset=3,
                  data=rng.choice([-1.0, 1.0], 100), epochs_per_symbol=10)
    return q, generate([q, i], FE, 0.5)


def test_acquire_and_track_q5(l5):
    q, x = l5
    a = acquire(x, 7, FE.fs_hz, FE.f_if_hz, spec=GPS_L5Q, noncoherent=10)
    assert a.detected and abs(a.doppler_hz - q.doppler_hz) <= 250
    assert abs(((a.code_phase_chips - q.code_phase_chips) + 5115) % 10230 - 5115) < 0.5
    assert not acquire(x, 8, FE.fs_hz, FE.f_if_hz, spec=GPS_L5Q, noncoherent=10).detected

    tr = Tracker(7, FE.fs_hz, FE.f_if_hz, a.doppler_hz, a.code_phase_chips, spec=GPS_L5Q)
    code_err, carr_err = [], []
    while tr.step(x):
        t = tr.pos / FE.fs_hz
        code_err.append(((q.chips_at(t) - tr.replica_code_chips() + 5115) % 10230) - 5115)
        carr_err.append((FE.f_if_hz + q.doppler_hz) * t + q.carrier_phase_cycles
                        - tr.replica_carrier_cycles())
    ce = np.array(code_err[SETTLE:])
    pe = np.array(carr_err[SETTLE:])
    # 1 L5 chip = 29.3 m: 0.02 chip ~ 0.6 m.
    assert abs(ce.mean()) < 0.02 and ce.std() < 0.02
    # Q5 rides on -sin: locked a quarter cycle (mod 1/2, Costas) from the cos-phase truth.
    assert pe.std() < 0.01
    assert abs((pe.mean() % 0.5) - 0.25) < 0.02
    ip = [r.ip for r in tr.records]
    qp = [r.qp for r in tr.records]
    assert q.cn0_dbhz - 2.0 < cn0_m2m4(ip[SETTLE:], qp[SETTLE:]) < q.cn0_dbhz + 0.5

    k = secondary_sync(ip, GPS_L5Q, start=100)
    assert k == q.secondary_offset
    # With NH20 wiped off, 20 epochs add coherently: the 20 ms prompt is ~20x one epoch.
    sec = 1 - 2 * np.array(GPS_L5Q.secondary)
    n0 = 120 - (120 + k) % 20          # first epoch with secondary bit index 0 after settling
    wiped = np.array(ip[n0:n0 + 20]) * sec
    assert abs(wiped.sum()) > 15 * np.mean(np.abs(ip[n0:n0 + 20]))
