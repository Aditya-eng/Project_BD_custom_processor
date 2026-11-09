"""SBAS L1 and QZSS L1 C/A on a simulated L1 band next to a GPS satellite: acquire each
from the extended C/A tables (IS-GPS-200N Table 6-I), track, find the symbol phase
(SBAS 2 ms symbols, QZSS 20 ms LNAV bits) and read the symbols back."""
import numpy as np
import pytest

from bdmodel import qzss, sbas
from bdmodel.acquisition import acquire
from bdmodel.gps_ca import CA_LEN
from bdmodel.signal_sim import FrontEnd
from bdmodel.signals import GPS_L1CA, QZSS_L1CA, SBAS_L1
from bdmodel.sim_generic import Component, generate
from bdmodel.tracking import Tracker, cn0_m2m4, symbol_phase

FE = FrontEnd(fs_hz=16e6, f_if_hz=4.3e6)
SETTLE = 150
HALF = CA_LEN / 2


@pytest.fixture(scope="module")
def l1():
    rng = np.random.default_rng(23)
    gps = Component(GPS_L1CA, 5, 46.0, -1720.0, 201.3, 0.1, symbol_offset=7,
                    data=rng.choice([-1.0, 1.0], 40), epochs_per_symbol=20)
    # EGNOS PRN 123 (EGNOS OS SDD issue 3.0 Table 2): GEO, small Doppler, 500 sps.
    geo = Component(SBAS_L1, 123, 43.0, 84.6, 777.7, 0.4, symbol_offset=1,
                    data=rng.choice([-1.0, 1.0], 400), epochs_per_symbol=sbas.EPOCHS_PER_SYMBOL)
    qzs = Component(QZSS_L1CA, 194, 45.0, 2210.5, 512.9, 0.8, symbol_offset=13,
                    data=rng.choice([-1.0, 1.0], 40), epochs_per_symbol=20)
    return gps, geo, qzs, generate([gps, geo, qzs], FE, 0.6, seed=4)


def _track(x, c):
    a = acquire(x, c.prn, FE.fs_hz, FE.f_if_hz, spec=c.spec, noncoherent=10)
    assert a.detected and abs(a.doppler_hz - c.doppler_hz) <= 250
    assert abs(((a.code_phase_chips - c.code_phase_chips) + HALF) % CA_LEN - HALF) < 0.5
    tr = Tracker(c.prn, FE.fs_hz, FE.f_if_hz, a.doppler_hz, a.code_phase_chips, spec=c.spec)
    ce, pe = [], []
    while tr.step(x):
        t = tr.pos / FE.fs_hz
        ce.append(((c.chips_at(t) - tr.replica_code_chips() + HALF) % CA_LEN) - HALF)
        pe.append((FE.f_if_hz + c.doppler_hz) * t + c.carrier_phase_cycles - tr.replica_carrier_cycles())
    ce, pe = np.array(ce[SETTLE:]), np.array(pe[SETTLE:])
    assert abs(ce.mean()) < 0.02 and ce.std() < 0.03
    assert pe.std() < 0.02
    off = pe.mean() % 0.5
    assert min(off, 0.5 - off) < 0.02
    ip = np.array([r.ip for r in tr.records], dtype=np.float64)
    qp = np.array([r.qp for r in tr.records], dtype=np.float64)
    assert c.cn0_dbhz - 2.0 < cn0_m2m4(ip[SETTLE:], qp[SETTLE:]) < c.cn0_dbhz + 0.5
    return ip


def _symbols_match(ip, k, n_per, data, start):
    n0 = start + (-(start + k)) % n_per
    m = (len(ip) - n0) // n_per
    got = np.sign(ip[n0:n0 + m * n_per].reshape(m, n_per).sum(axis=1))
    want = data[(n0 + k) // n_per:(n0 + k) // n_per + m]
    return m, np.mean(got == want)


def test_prn_ranges():
    assert list(sbas.SBAS_PRNS) == list(range(120, 159))
    assert list(qzss.QZSS_PRNS) == list(range(193, 203))
    assert sbas.SYMBOL_RATE_SPS == 2 * sbas.DATA_RATE_BPS == 500


def test_sbas_geo_500sps(l1):
    _, geo, _, x = l1
    ip = _track(x, geo)
    k = sbas.symbol_phase(ip, start=SETTLE)
    assert k == geo.symbol_offset
    m, agree = _symbols_match(ip, k, sbas.EPOCHS_PER_SYMBOL, geo.data, SETTLE)
    assert m >= 200 and agree in (0.0, 1.0)


def test_qzss_l1ca_lnav_bits(l1):
    _, _, qzs, x = l1
    ip = _track(x, qzs)
    k = symbol_phase(ip, 20, start=SETTLE)
    assert k == qzs.symbol_offset
    m, agree = _symbols_match(ip, k, 20, qzs.data, SETTLE)
    assert m >= 20 and agree in (0.0, 1.0)


def test_gps_unaffected_and_absent_prns_not_detected(l1):
    gps, _, _, x = l1
    _track(x, gps)
    for prn, spec in ((124, SBAS_L1), (195, QZSS_L1CA)):
        assert not acquire(x, prn, FE.fs_hz, FE.f_if_hz, spec=spec, noncoherent=10).detected
