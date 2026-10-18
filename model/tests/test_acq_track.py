"""End-to-end software receiver slice on synthetic signals with known truth.

Acceptance thresholds trace to docs/REQUIREMENTS.md (REQ-TRK-*, REQ-ACQ-*).
"""
import numpy as np
import pytest

from bdmodel.acquisition import acquire
from bdmodel.gps_ca import CA_LEN
from bdmodel.signal_sim import FrontEnd, SatSignal, code_chips_at, generate
from bdmodel.tracking import LoopConfig, Tracker, bit_sync, cn0_m2m4

FE = FrontEnd(fs_hz=16.0e6, f_if_hz=4.0e6)   # deliberately non-commensurate with 1.023 MHz
SETTLE = 300                                  # epochs ignored while loops settle


@pytest.fixture(scope="module")
def scenario():
    rng = np.random.default_rng(7)
    sats = [SatSignal(5, 45.0, 1234.5, 345.67, 0.3, 0.0, rng.choice([-1, 1], 50)),
            SatSignal(12, 42.0, -2800.0, 900.1, 0.1, 0.0, rng.choice([-1, 1], 50))]
    return sats, generate(sats, FE, 0.6)


def test_acquisition_finds_both(scenario):
    sats, x = scenario
    for s in sats:
        a = acquire(x, s.prn, FE.fs_hz, FE.f_if_hz)
        assert a.detected
        assert abs(a.doppler_hz - s.doppler_hz) <= 250
        err = ((a.code_phase_chips - s.code_phase_chips) + 511.5) % CA_LEN - 511.5
        assert abs(err) <= 0.5


def test_absent_prn_not_detected(scenario):
    _, x = scenario
    assert not acquire(x, 20, FE.fs_hz, FE.f_if_hz).detected


@pytest.mark.parametrize("delay", [0, 1])
@pytest.mark.parametrize("idx", [0, 1])
def test_tracking_against_truth(scenario, idx, delay):
    sats, x = scenario
    s = sats[idx]
    a = acquire(x, s.prn, FE.fs_hz, FE.f_if_hz)
    tr = Tracker(s.prn, FE.fs_hz, FE.f_if_hz, a.doppler_hz, a.code_phase_chips,
                 LoopConfig(update_delay_epochs=delay))
    code_err, carr_err = [], []
    while tr.step(x):
        t = tr.pos / FE.fs_hz
        code_err.append(((code_chips_at(s, np.array([t]))[0] - tr.replica_code_chips() + 511.5)
                         % CA_LEN) - 511.5)
        carr_err.append((FE.f_if_hz + s.doppler_hz) * t + s.carrier_phase_cycles
                        - tr.replica_carrier_cycles())
    code_err = np.array(code_err[SETTLE:])
    carr_err = np.array(carr_err[SETTLE:])

    # Code: unbiased and quiet (1 chip = 293 m; 0.02 chip ~ 6 m).
    assert abs(code_err.mean()) < 0.02 and code_err.std() < 0.02
    # Carrier: locked to a constant offset that is a multiple of 1/2 cycle (Costas).
    assert carr_err.std() < 0.01
    off = carr_err.mean() % 0.5
    assert min(off, 0.5 - off) < 0.02
    # Doppler estimate.
    dopp = np.mean([r.carr_freq_hz for r in tr.records[SETTLE:]]) - FE.f_if_hz
    assert abs(dopp - s.doppler_hz) < 0.5
    # C/N0 estimate within the expected 2-bit + LUT loss window.
    ip = [r.ip for r in tr.records]
    qp = [r.qp for r in tr.records]
    cn0 = cn0_m2m4(ip[SETTLE:], qp[SETTLE:])
    assert s.cn0_dbhz - 2.0 < cn0 < s.cn0_dbhz + 0.5
    # Bit sync and nav-bit recovery (up to the Costas sign ambiguity).
    bs = bit_sync(ip)
    assert bs == 0
    n_bits = (len(ip) - bs) // 20
    sums = np.array([sum(ip[bs + 20 * k: bs + 20 * k + 20]) for k in range(n_bits)])
    dec = np.sign(sums)[5:]
    truth = s.nav_bits[5:n_bits]
    assert np.all(dec == truth) or np.all(dec == -truth)
