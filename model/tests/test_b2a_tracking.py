"""BeiDou B2a: pilot (quadrature, per-PRN Weil secondary) and data (200 sps, 5-bit secondary)
acquired and tracked on a simulated signal; secondary sync and symbol recovery."""
import numpy as np
import pytest

from bdmodel.acquisition import acquire, refine_doppler
from bdmodel.bds_b2a import B2A_LEN, DATA_EPOCHS_PER_SYMBOL
from bdmodel.signal_sim import FrontEnd
from bdmodel.signals import BDS_B2A_D, BDS_B2A_P, secondary_sync
from bdmodel.sim_generic import Component, generate
from bdmodel.tracking import Tracker, cn0_m2m4

FE = FrontEnd(fs_hz=50e6, f_if_hz=13.0e6)
PRN, FD, CP = 62, -2210.4, 777.6          # 62: data and pilot initial values differ
SETTLE = 300
HALF = B2A_LEN / 2


@pytest.fixture(scope="module")
def b2a():
    rng = np.random.default_rng(9)
    p = Component(BDS_B2A_P, PRN, 45.0, FD, CP, 0.15, quadrature=True, secondary_offset=71)
    d = Component(BDS_B2A_D, PRN, 45.0, FD, CP, 0.15, secondary_offset=3, symbol_offset=3,
                  data=rng.choice([-1.0, 1.0], 200), epochs_per_symbol=DATA_EPOCHS_PER_SYMBOL)
    return p, d, generate([p, d], FE, 0.5)


def _track(x, comp):
    spec = comp.spec
    a = acquire(x, PRN, FE.fs_hz, FE.f_if_hz, spec=spec, noncoherent=10)
    assert a.detected
    assert abs(((a.code_phase_chips - comp.code_phase_chips) + HALF) % B2A_LEN - HALF) < 0.5
    a = refine_doppler(x, a, FE.fs_hz, FE.f_if_hz, spec=spec, blocks=10)
    tr = Tracker(PRN, FE.fs_hz, FE.f_if_hz, a.doppler_hz, a.code_phase_chips, spec=spec)
    ce, pe = [], []
    while tr.step(x):
        t = tr.pos / FE.fs_hz
        ce.append(((comp.chips_at(t) - tr.replica_code_chips() + HALF) % B2A_LEN) - HALF)
        pe.append((FE.f_if_hz + FD) * t + comp.carrier_phase_cycles - tr.replica_carrier_cycles())
    ce, pe = np.array(ce[SETTLE:]), np.array(pe[SETTLE:])
    assert abs(ce.mean()) < 0.02 and ce.std() < 0.02           # 1 chip = 29.3 m
    ip = np.array([r.ip for r in tr.records], dtype=np.float64)
    qp = np.array([r.qp for r in tr.records], dtype=np.float64)
    assert comp.cn0_dbhz - 2.0 < cn0_m2m4(ip[SETTLE:], qp[SETTLE:]) < comp.cn0_dbhz + 0.5
    return ip, pe


def test_pilot(b2a):
    p, _, x = b2a
    ip, pe = _track(x, p)
    assert pe.std() < 0.01 and abs((pe.mean() % 0.5) - 0.25) < 0.02       # quadrature
    assert secondary_sync(ip, BDS_B2A_P, start=100, prn=PRN) == p.secondary_offset
    assert secondary_sync(ip, BDS_B2A_P, start=100, prn=PRN + 1) is None


def test_data(b2a):
    _, d, x = b2a
    ip, pe = _track(x, d)
    off = pe.mean() % 0.5
    assert pe.std() < 0.01 and min(off, 0.5 - off) < 0.02
    k = secondary_sync(ip, BDS_B2A_D, start=SETTLE, prn=PRN)
    assert k == d.secondary_offset
    n = DATA_EPOCHS_PER_SYMBOL
    sec = 1 - 2 * np.array(BDS_B2A_D.secondary_code(PRN))
    n0 = SETTLE + (-(SETTLE + k)) % n
    m = (len(ip) - n0) // n
    sym = (ip[n0:n0 + n * m] * np.tile(sec, m)).reshape(m, n).sum(axis=1)
    want = d.data[(n0 + k) // n:(n0 + k) // n + m]
    assert m > 30 and np.mean(np.sign(sym) == want) in (0.0, 1.0)
