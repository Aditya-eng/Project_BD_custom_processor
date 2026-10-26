"""Galileo E1 (CBOC broadcast, BOC(1,1) replica) and E5a on simulated signals."""
import numpy as np
import pytest

from bdmodel.acquisition import acquire, refine_doppler
from bdmodel.signal_sim import FrontEnd
from bdmodel.signals import GAL_E1B, GAL_E1C, GAL_E5AI, GAL_E5AQ, secondary_sync
from bdmodel.sim_generic import Component, generate
from bdmodel.tracking import LoopConfig, Tracker, cn0_m2m4


def _track(x, fe, comp, acq, cfg=None):
    spec = comp.spec
    L = spec.code_len
    tr = Tracker(comp.prn, fe.fs_hz, fe.f_if_hz, acq.doppler_hz, acq.code_phase_chips, spec=spec,
                 cfg=cfg or LoopConfig())
    ce, pe = [], []
    while tr.step(x):
        t = tr.pos / fe.fs_hz
        ce.append(((comp.chips_at(t) - tr.replica_code_chips() + L / 2) % L) - L / 2)
        pe.append((fe.f_if_hz + comp.doppler_hz) * t + comp.carrier_phase_cycles
                  - tr.replica_carrier_cycles())
    return tr, np.array(ce), np.array(pe)


@pytest.fixture(scope="module")
def e1():
    fe = FrontEnd(fs_hz=32e6, f_if_hz=8.5e6)        # CBOC(6,1) needs > +/-7 MHz
    rng = np.random.default_rng(9)
    b = Component(GAL_E1B, 11, 45.0, 1777.7, 1234.3, 0.2, data=rng.choice([-1.0, 1.0], 400))
    c = Component(GAL_E1C, 11, 45.0, 1777.7, 1234.3, 0.7, secondary_offset=17)
    return fe, c, generate([b, c], fe, 1.2)


def test_e1c_pilot(e1):
    fe, c, x = e1
    a = acquire(x, 11, fe.fs_hz, fe.f_if_hz, spec=GAL_E1C, doppler_step_hz=62.5, noncoherent=4)
    assert a.detected
    # BOC(1,1) side peaks sit at +/-0.5 chip: acquisition must land on the main peak.
    assert abs(((a.code_phase_chips - c.code_phase_chips) + 2046) % 4092 - 2046) < 0.15
    assert not acquire(x, 12, fe.fs_hz, fe.f_if_hz, spec=GAL_E1C, doppler_step_hz=62.5,
                       noncoherent=4).detected
    # Coarse blocks straddle CS25 sign flips; the epoch-aligned refinement must bring the
    # Doppler inside the 4 ms FLL pull-in range (+/-62.5 Hz) - in practice to a few Hz.
    a = refine_doppler(x, a, fe.fs_hz, fe.f_if_hz, spec=GAL_E1C)
    assert abs(a.doppler_hz - c.doppler_hz) < 15

    tr, ce, pe = _track(x, fe, c, a, LoopConfig(half_spacing_chips=0.1))
    S = 150                                            # epochs (4 ms) left to settle
    ce, pe = ce[S:], pe[S:]
    assert abs(ce.mean()) < 0.01 and ce.std() < 0.01   # 0.01 chip ~ 3 m
    assert pe.std() < 0.01
    off = pe.mean() % 0.5
    assert min(off, 0.5 - off) < 0.02
    ip = [r.ip for r in tr.records]
    qp = [r.qp for r in tr.records]
    # Expected losses: 2-bit ADC, carrier LUT, BOC(1,1) replica vs CBOC (~0.4 dB).
    assert c.cn0_dbhz - 2.0 < cn0_m2m4(ip[S:], qp[S:], T=GAL_E1C.epoch_s) < c.cn0_dbhz
    assert secondary_sync(ip, GAL_E1C, start=100, prn=11) == c.secondary_offset


@pytest.fixture(scope="module")
def e5a():
    fe = FrontEnd(fs_hz=50e6, f_if_hz=13.0e6)
    rng = np.random.default_rng(5)
    q = Component(GAL_E5AQ, 19, 45.0, -987.6, 8000.5, 0.3, quadrature=True, secondary_offset=61)
    i = Component(GAL_E5AI, 19, 45.0, -987.6, 8000.5, 0.3, secondary_offset=7,
                  data=rng.choice([-1.0, 1.0], 40), epochs_per_symbol=20)
    return fe, q, generate([q, i], fe, 0.5)


def test_e5aq_pilot(e5a):
    fe, q, x = e5a
    a = acquire(x, 19, fe.fs_hz, fe.f_if_hz, spec=GAL_E5AQ, noncoherent=10)
    assert a.detected
    a = refine_doppler(x, a, fe.fs_hz, fe.f_if_hz, spec=GAL_E5AQ, blocks=10)
    tr, ce, pe = _track(x, fe, q, a)
    ce, pe = ce[300:], pe[300:]
    assert abs(ce.mean()) < 0.02 and ce.std() < 0.02
    assert pe.std() < 0.01 and abs((pe.mean() % 0.5) - 0.25) < 0.02    # quadrature pilot
    ip = [r.ip for r in tr.records]
    # CS100 is per satellite: the right PRN's code syncs, a neighbour's does not.
    assert secondary_sync(ip, GAL_E5AQ, start=100, prn=19) == q.secondary_offset
    assert secondary_sync(ip, GAL_E5AQ, start=100, prn=20) is None
