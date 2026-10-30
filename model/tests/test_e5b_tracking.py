"""Galileo E5b (tracked as a BPSK(10) sideband): E5b-Q pilot with CS100(n+50), E5b-I data
(250 sps) with CS4, on a simulated I + Q signal."""
import numpy as np
import pytest

from bdmodel.acquisition import acquire, refine_doppler
from bdmodel.galileo import E5BI_EPOCHS_PER_SYMBOL, E5_LEN, e5bq_secondary, secondary
from bdmodel.signal_sim import FrontEnd
from bdmodel.signals import GAL_E5AQ, GAL_E5BI, GAL_E5BQ, secondary_sync
from bdmodel.sim_generic import Component, generate
from bdmodel.tracking import Tracker, cn0_m2m4

FE = FrontEnd(fs_hz=50e6, f_if_hz=13.0e6)
PRN, FD, CP = 27, 1733.2, 6100.75
SETTLE = 300
HALF = E5_LEN / 2


def test_secondary_assignment():
    # ICD 3.6: "CS100(n+50) for E5b-Q (i.e. CS10051 to SVID 1)"; CS41 for E5b-I.
    assert e5bq_secondary(1) == secondary(100, 51) and e5bq_secondary(36) == secondary(100, 86)
    assert GAL_E5BI.secondary_code(5) == secondary(4, 1) == (1, 1, 1, 0)
    assert GAL_E5BQ.secondary_code(PRN) != GAL_E5AQ.secondary_code(PRN)


@pytest.fixture(scope="module")
def e5b():
    rng = np.random.default_rng(8)
    q = Component(GAL_E5BQ, PRN, 45.0, FD, CP, 0.4, quadrature=True, secondary_offset=37)
    i = Component(GAL_E5BI, PRN, 45.0, FD, CP, 0.4, secondary_offset=2, symbol_offset=2,
                  data=rng.choice([-1.0, 1.0], 200), epochs_per_symbol=E5BI_EPOCHS_PER_SYMBOL)
    return q, i, generate([q, i], FE, 0.5)


def _track(x, comp, spec):
    a = acquire(x, PRN, FE.fs_hz, FE.f_if_hz, spec=spec, noncoherent=10)
    assert a.detected
    assert abs(((a.code_phase_chips - comp.code_phase_chips) + HALF) % E5_LEN - HALF) < 0.5
    a = refine_doppler(x, a, FE.fs_hz, FE.f_if_hz, spec=spec, blocks=10)
    tr = Tracker(PRN, FE.fs_hz, FE.f_if_hz, a.doppler_hz, a.code_phase_chips, spec=spec)
    ce, pe = [], []
    while tr.step(x):
        t = tr.pos / FE.fs_hz
        ce.append(((comp.chips_at(t) - tr.replica_code_chips() + HALF) % E5_LEN) - HALF)
        pe.append((FE.f_if_hz + FD) * t + comp.carrier_phase_cycles - tr.replica_carrier_cycles())
    ce, pe = np.array(ce[SETTLE:]), np.array(pe[SETTLE:])
    assert abs(ce.mean()) < 0.02 and ce.std() < 0.02           # 1 chip = 29.3 m
    ip = np.array([r.ip for r in tr.records], dtype=np.float64)
    qp = np.array([r.qp for r in tr.records], dtype=np.float64)
    assert comp.cn0_dbhz - 2.0 < cn0_m2m4(ip[SETTLE:], qp[SETTLE:]) < comp.cn0_dbhz + 0.5
    return ip, pe


def test_e5bq_pilot(e5b):
    q, _, x = e5b
    ip, pe = _track(x, q, GAL_E5BQ)
    assert pe.std() < 0.01 and abs((pe.mean() % 0.5) - 0.25) < 0.02       # quadrature
    assert secondary_sync(ip, GAL_E5BQ, start=100, prn=PRN) == q.secondary_offset
    # The E5a-Q code of the same SVID (CS100(n), not n+50) must not sync.
    assert secondary_sync(ip, GAL_E5AQ, start=100, prn=PRN) is None


def test_e5bi_data(e5b):
    _, i, x = e5b
    ip, pe = _track(x, i, GAL_E5BI)
    off = pe.mean() % 0.5
    assert pe.std() < 0.01 and min(off, 0.5 - off) < 0.02
    # CS4 sync with 250 sps data flipping the sign between CS4 periods.
    k = secondary_sync(ip, GAL_E5BI, start=SETTLE, prn=PRN)
    assert k == i.secondary_offset
    sec = 1 - 2 * np.array(GAL_E5BI.secondary_code(PRN))
    n0 = SETTLE + (-(SETTLE + k)) % 4
    m = (len(ip) - n0) // 4
    sym = (ip[n0:n0 + 4 * m] * np.tile(sec, m)).reshape(m, 4).sum(axis=1)
    want = i.data[(n0 + k) // 4:(n0 + k) // 4 + m]
    assert m > 40 and np.mean(np.sign(sym) == want) in (0.0, 1.0)
