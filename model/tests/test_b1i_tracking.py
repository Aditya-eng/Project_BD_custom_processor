"""BeiDou B1I: acquire and track a MEO (D1 + NH20) and a GEO (D2, 500 bps) satellite,
sync the NH code / bit phase and read the data bits back."""
import numpy as np
import pytest

from bdmodel.acquisition import acquire
from bdmodel.bds_b1i import B1I_LEN, NH20, bit_phase, epochs_per_bit
from bdmodel.signal_sim import FrontEnd
from bdmodel.signals import BDS_B1I, secondary_sync
from bdmodel.sim_generic import Component, generate
from bdmodel.tracking import Tracker, cn0_m2m4

FE = FrontEnd(fs_hz=16e6, f_if_hz=4.3e6)
SETTLE = 150
HALF = B1I_LEN / 2


@pytest.fixture(scope="module")
def b1i():
    rng = np.random.default_rng(11)
    meo = Component(BDS_B1I, 21, 45.0, 2876.4, 1500.4, 0.2, secondary_offset=13,
                    symbol_offset=13, data=rng.choice([-1.0, 1.0], 40), epochs_per_symbol=20)
    geo = Component(BDS_B1I, 3, 44.0, -151.9, 333.7, 0.6, symbol_offset=1,
                    data=rng.choice([-1.0, 1.0], 400), epochs_per_symbol=2)
    return meo, geo, generate([meo, geo], FE, 0.6)


def _track(x, c):
    a = acquire(x, c.prn, FE.fs_hz, FE.f_if_hz, spec=BDS_B1I, noncoherent=10)
    assert a.detected and abs(a.doppler_hz - c.doppler_hz) <= 250
    assert abs(((a.code_phase_chips - c.code_phase_chips) + HALF) % B1I_LEN - HALF) < 0.5
    tr = Tracker(c.prn, FE.fs_hz, FE.f_if_hz, a.doppler_hz, a.code_phase_chips, spec=BDS_B1I)
    ce, pe = [], []
    while tr.step(x):
        t = tr.pos / FE.fs_hz
        ce.append(((c.chips_at(t) - tr.replica_code_chips() + HALF) % B1I_LEN) - HALF)
        pe.append((FE.f_if_hz + c.doppler_hz) * t + c.carrier_phase_cycles - tr.replica_carrier_cycles())
    ce, pe = np.array(ce[SETTLE:]), np.array(pe[SETTLE:])
    # 1 B1I chip = 146.5 m.
    assert abs(ce.mean()) < 0.02 and ce.std() < 0.02
    assert pe.std() < 0.02
    off = pe.mean() % 0.5
    assert min(off, 0.5 - off) < 0.02
    ip = np.array([r.ip for r in tr.records], dtype=np.float64)
    qp = np.array([r.qp for r in tr.records], dtype=np.float64)
    assert c.cn0_dbhz - 2.0 < cn0_m2m4(ip[SETTLE:], qp[SETTLE:]) < c.cn0_dbhz + 0.5
    return ip


def _bits_match(ip, k, n_per_bit, data, start):
    """Sum whole bits from the first boundary after `start`; compare with the truth."""
    n0 = start + (-(start + k)) % n_per_bit
    m = (len(ip) - n0) // n_per_bit
    sums = ip[n0:n0 + m * n_per_bit].reshape(m, n_per_bit)
    got = np.sign(sums.sum(axis=1))
    want = data[(n0 + k) // n_per_bit:(n0 + k) // n_per_bit + m]
    agree = np.mean(got == want)
    return m, agree


def test_meo_d1_nh20(b1i):
    meo, _, x = b1i
    ip = _track(x, meo)
    assert not acquire(x, 22, FE.fs_hz, FE.f_if_hz, spec=BDS_B1I, noncoherent=10).detected
    k = secondary_sync(ip, BDS_B1I, start=SETTLE, prn=meo.prn)
    assert k == meo.secondary_offset
    # The NH code is aligned with the data bits, so NH sync is also bit sync.
    sec = 1 - 2 * np.array(NH20)
    wiped = ip * sec[(np.arange(len(ip)) + k) % 20]
    m, agree = _bits_match(wiped, k, epochs_per_bit(meo.prn), meo.data, SETTLE)
    assert m >= 20 and agree in (0.0, 1.0)


def test_geo_d2(b1i):
    _, geo, x = b1i
    ip = _track(x, geo)
    assert BDS_B1I.secondary_code(geo.prn) is None
    k = bit_phase(ip, epochs_per_bit(geo.prn), start=SETTLE)
    assert k == geo.symbol_offset
    m, agree = _bits_match(ip, k, 2, geo.data, SETTLE)
    assert m >= 200 and agree in (0.0, 1.0)
