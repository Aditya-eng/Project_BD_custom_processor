"""BeiDou B1C: pilot (QMBOC as broadcast, BOC(1,1) replica, quadrature) and data (BOC(1,1),
100 sps, in phase together with the pilot's BOC(6,1) part) on a simulated signal."""
import numpy as np
import pytest

from bdmodel.acquisition import acquire, refine_doppler
from bdmodel.bds_b1c import B1C_LEN
from bdmodel.signal_sim import FrontEnd
from bdmodel.signals import BDS_B1C_D, BDS_B1C_P
from bdmodel.sim_generic import Component, generate
from bdmodel.tracking import LoopConfig, Tracker, cn0_m2m4

FE = FrontEnd(fs_hz=32e6, f_if_hz=8.5e6)
PRN, FD, CP = 33, 1876.3, 4321.4
S = 40                                       # 10 ms epochs
HALF = B1C_LEN / 2
CFG = LoopConfig(half_spacing_chips=0.1, fll_pullin_ms=30)


@pytest.fixture(scope="module")
def b1c():
    rng = np.random.default_rng(12)
    p = Component(BDS_B1C_P, PRN, 45.0, FD, CP, 0.35, quadrature=True, secondary_offset=901)
    d = Component(BDS_B1C_D, PRN, 45.0 - 4.77, FD, CP, 0.35,        # data:pilot = 1:3
                  data=rng.choice([-1.0, 1.0], 200))
    return p, d, generate([p, d], FE, 1.2)


def _track(x, comp, spec):
    # 10 ms codes: aid the search with the B1I / GPS L1 Doppler of the same satellite.
    a = acquire(x, PRN, FE.fs_hz, FE.f_if_hz, spec=spec, doppler_max_hz=300,
                doppler_step_hz=25, noncoherent=2, doppler_center_hz=FD - 60.0)
    assert a.detected
    assert abs(((a.code_phase_chips - comp.code_phase_chips) + HALF) % B1C_LEN - HALF) < 0.15
    a = refine_doppler(x, a, FE.fs_hz, FE.f_if_hz, spec=spec, blocks=4)
    assert abs(a.doppler_hz - FD) < 10
    tr = Tracker(PRN, FE.fs_hz, FE.f_if_hz, a.doppler_hz, a.code_phase_chips, spec=spec, cfg=CFG)
    ce, pe = [], []
    while tr.step(x):
        t = tr.pos / FE.fs_hz
        ce.append(((comp.chips_at(t) - tr.replica_code_chips() + HALF) % B1C_LEN) - HALF)
        pe.append((FE.f_if_hz + FD) * t + comp.carrier_phase_cycles - tr.replica_carrier_cycles())
    ce, pe = np.array(ce[S:]), np.array(pe[S:])
    assert abs(ce.mean()) < 0.01 and ce.std() < 0.01            # 1 chip = 293 m
    ip = np.array([r.ip for r in tr.records], dtype=np.float64)
    qp = np.array([r.qp for r in tr.records], dtype=np.float64)
    return ip, qp, pe


def test_qmboc_power_split():
    """Strong pilot, 8-bit ADC (noise ~0.2% of the correlation): BOC(1,1) sits in quadrature
    with 29/33 of the pilot power, BOC(6,1) in phase with 4/33 (ICD eq. 4-10/4-11)."""
    fe = FrontEnd(fs_hz=32e6, f_if_hz=8.5e6, adc_bits=8)
    p = Component(BDS_B1C_P, PRN, 75.0, 0.0, 100.0, 0.0, quadrature=True)
    x = generate([p], fe, 0.0105, seed=3).astype(np.float64)
    n = int(fe.fs_hz * 0.01)
    t = np.arange(n) / fe.fs_hz
    chips = p.code_phase_chips + t * BDS_B1C_P.chip_rate
    code = 1.0 - 2.0 * BDS_B1C_P.code(PRN)[np.floor(chips).astype(np.int64) % B1C_LEN]
    frac = chips % 1.0
    sc1 = np.where(frac < 0.5, 1.0, -1.0)
    sc6 = np.where(np.floor(frac * 12).astype(np.int64) % 2 == 0, 1.0, -1.0)
    ph = 2 * np.pi * fe.f_if_hz * t
    i_car, q_car = np.cos(ph), -np.sin(ph)
    corr = {(sc, car): abs(np.sum(x[:n] * code * s * c))
            for sc, s in (("b1", sc1), ("b6", sc6)) for car, c in (("I", i_car), ("Q", q_car))}
    assert abs(corr["b1", "Q"] / corr["b6", "I"] - np.sqrt(29 / 4)) < 0.03
    assert corr["b1", "I"] < 0.01 * corr["b1", "Q"] and corr["b6", "Q"] < 0.01 * corr["b6", "I"]


def test_pilot(b1c):
    p, _, x = b1c
    ip, qp, pe = _track(x, p, BDS_B1C_P)
    assert pe.std() < 0.01 and abs((pe.mean() % 0.5) - 0.25) < 0.02       # quadrature
    # Expected about 45 - 0.56 (QMBOC) - ADC. The M2M4 spread over these 80 epochs is about
    # +/-1 dB (3 s runs: 43.2 and 44.3), so the 0.56 dB is checked by test_qmboc_power_split.
    assert p.cn0_dbhz - 2.5 < cn0_m2m4(ip[S:], qp[S:], T=BDS_B1C_P.epoch_s) < p.cn0_dbhz + 0.5


def test_data(b1c):
    _, d, x = b1c
    ip, qp, pe = _track(x, d, BDS_B1C_D)
    off = pe.mean() % 0.5
    assert pe.std() < 0.02 and min(off, 0.5 - off) < 0.02
    # 100 sps: one symbol per 10 ms primary period (no secondary code on the data component).
    assert np.mean(np.sign(ip[S:]) == d.data[S:len(ip)]) in (0.0, 1.0)
    assert d.cn0_dbhz - 2.0 < cn0_m2m4(ip[S:], qp[S:], T=BDS_B1C_D.epoch_s) < d.cn0_dbhz + 0.5
