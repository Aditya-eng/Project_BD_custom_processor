"""GPS L1C: aided acquisition and L1CP pilot tracking on a simulated TMBOC signal."""
import numpy as np

from bdmodel.acquisition import acquire, refine_doppler
from bdmodel.signal_sim import FrontEnd
from bdmodel.signals import GPS_L1CD, GPS_L1CP
from bdmodel.sim_generic import Component, generate
from bdmodel.tracking import LoopConfig, Tracker, cn0_m2m4


def test_l1cp_pilot():
    fe = FrontEnd(fs_hz=32e6, f_if_hz=8.5e6)
    rng = np.random.default_rng(3)
    cp, fd = 5000.25, -1432.1
    p = Component(GPS_L1CP, 24, 45.0, fd, cp, 0.15, secondary_offset=900)
    # 75 % / 25 % power split between pilot and data.
    d = Component(GPS_L1CD, 24, 45.0 - 4.77, fd, cp, 0.15, data=rng.choice([-1.0, 1.0], 200))
    x = generate([p, d], fe, 1.2)

    # 10 ms codes make a blind search slow; aid it with the L1 C/A Doppler of the same SV.
    a = acquire(x, 24, fe.fs_hz, fe.f_if_hz, spec=GPS_L1CP, doppler_max_hz=300,
                doppler_step_hz=25, noncoherent=2, doppler_center_hz=-1500.0)
    assert a.detected
    assert abs(((a.code_phase_chips - cp) + 5115) % 10230 - 5115) < 0.15   # main BOC peak
    a = refine_doppler(x, a, fe.fs_hz, fe.f_if_hz, spec=GPS_L1CP, blocks=4)
    assert abs(a.doppler_hz - fd) < 10                       # within the +/-25 Hz FLL range

    tr = Tracker(24, fe.fs_hz, fe.f_if_hz, a.doppler_hz, a.code_phase_chips, spec=GPS_L1CP,
                 cfg=LoopConfig(half_spacing_chips=0.1, fll_pullin_ms=40))
    ce, pe = [], []
    while tr.step(x):
        t = tr.pos / fe.fs_hz
        ce.append(((p.chips_at(t) - tr.replica_code_chips() + 5115) % 10230) - 5115)
        pe.append((fe.f_if_hz + fd) * t + p.carrier_phase_cycles - tr.replica_carrier_cycles())
    S = 60                                                    # 10 ms epochs
    ce, pe = np.array(ce[S:]), np.array(pe[S:])
    assert abs(ce.mean()) < 0.01 and ce.std() < 0.01
    assert pe.std() < 0.01
    off = pe.mean() % 0.5
    assert min(off, 0.5 - off) < 0.02
    ip = [r.ip for r in tr.records]
    qp = [r.qp for r in tr.records]
    # TMBOC vs BOC(1,1) replica: 4 of 33 chips do not correlate (-1.1 dB) + 2-bit ADC.
    assert p.cn0_dbhz - 2.5 < cn0_m2m4(ip[S:], qp[S:], T=GPS_L1CP.epoch_s) < p.cn0_dbhz - 0.5
