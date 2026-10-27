"""GPS L2C: aided CM acquisition and CM tracking (TDM-gated replica) on a simulated
CM + CL chip-multiplexed signal."""
import dataclasses

import numpy as np

from bdmodel.acquisition import acquire, refine_doppler
from bdmodel.gps_l2c import CM_LEN
from bdmodel.signal_sim import FrontEnd
from bdmodel.signals import GPS_L2CL, GPS_L2CM, replica
from bdmodel.sim_generic import Component, generate
from bdmodel.tracking import LoopConfig, Tracker, cn0_m2m4

FE = FrontEnd(fs_hz=8e6, f_if_hz=2.1e6)
PRN, CP, FD, CN0 = 14, 3000.3, 1104.6, 45.0
CL_PERIOD = 23                      # CM period (of 75) the run starts in, within the CL period


def _signal(seconds, rng, cn0=CN0):
    cm = Component(GPS_L2CM, PRN, cn0, FD, CP, 0.3, data=rng.choice([-1.0, 1.0], 100))
    cl = Component(GPS_L2CL, PRN, cn0, FD, CP + CL_PERIOD * CM_LEN, 0.3)
    return cm, cl, generate([cm, cl], FE, seconds, seed=7)


def _corr(x, spec, chip0):
    """|correlation| over one CM period with known carrier (no loops)."""
    n = int(FE.fs_hz * 0.02)
    t = np.arange(n) / FE.fs_hz
    lo = np.exp(-2j * np.pi * ((FE.f_if_hz + FD) * t + 0.3))
    rate_scale = 1 + FD / spec.carrier_hz
    fs_eff = FE.fs_hz / rate_scale
    return abs(np.sum(x[:n] * lo * replica(spec, PRN, n, fs_eff, chip0)))


def test_l2c_slots_and_codes():
    cm, cl, x = _signal(0.021, np.random.default_rng(1), cn0=52.0)
    on = _corr(x, GPS_L2CM, CP)
    assert on > 8 * _corr(x, dataclasses.replace(GPS_L2CM, tdm_slot=1), CP)   # CM is first
    assert on > 8 * _corr(x, GPS_L2CM, CP + 0.75)                               # past the slot
    pilot = _corr(x, GPS_L2CL, cl.code_phase_chips)
    assert pilot > 8 * _corr(x, GPS_L2CL, cl.code_phase_chips + CM_LEN)        # CL period phase


def test_l2cm_tracking():
    rng = np.random.default_rng(5)
    cm, cl, x = _signal(1.2, rng)

    # 20 ms codes: aid the search with a Doppler predicted from L1 C/A.
    a = acquire(x, PRN, FE.fs_hz, FE.f_if_hz, spec=GPS_L2CM, doppler_max_hz=200,
                doppler_step_hz=20, noncoherent=2, doppler_center_hz=FD + 37.0)
    assert a.detected
    assert abs(((a.code_phase_chips - CP) + CM_LEN / 2) % CM_LEN - CM_LEN / 2) < 0.1
    a = refine_doppler(x, a, FE.fs_hz, FE.f_if_hz, spec=GPS_L2CM, blocks=4, step_hz=2)
    assert abs(a.doppler_hz - FD) < 5

    tr = Tracker(PRN, FE.fs_hz, FE.f_if_hz, a.doppler_hz, a.code_phase_chips, spec=GPS_L2CM,
                 cfg=LoopConfig(pll_bw_hz=10.0, fll_pullin_ms=15, dll_bw_hz=1.0,
                                half_spacing_chips=0.25))
    ce, pe = [], []
    while tr.step(x):
        t = tr.pos / FE.fs_hz
        ce.append(((cm.chips_at(t) - tr.replica_code_chips() + CM_LEN / 2) % CM_LEN) - CM_LEN / 2)
        pe.append((FE.f_if_hz + FD) * t + cm.carrier_phase_cycles - tr.replica_carrier_cycles())
    S = 25                                                       # 20 ms epochs
    ce, pe = np.array(ce[S:]), np.array(pe[S:])
    assert len(ce) > 25
    assert abs(ce.mean()) < 0.02 and ce.std() < 0.02            # CM chips (586 m)
    assert pe.std() < 0.02
    off = pe.mean() % 0.5
    assert min(off, 0.5 - off) < 0.03

    # One CNAV symbol per CM period: prompt signs reproduce them (Costas sign ambiguity).
    ip = np.array([r.ip for r in tr.records], dtype=np.float64)
    qp = np.array([r.qp for r in tr.records], dtype=np.float64)
    agree = np.mean(np.sign(ip[S:]) == cm.data[S:len(ip)])
    assert agree in (0.0, 1.0)
    # CM holds half the composite power (-3 dB). At 8 MHz the 2-bit ADC loss is below the
    # estimator spread (longer runs give 42.0-42.2). An ungated replica would add the CL
    # half's noise and read ~3 dB lower.
    assert CN0 - 4.0 < cn0_m2m4(ip[S:], qp[S:], T=GPS_L2CM.epoch_s) < CN0 - 1.5
