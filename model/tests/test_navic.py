"""NavIC L5 SPS. The per-PRN code table is generated locally from the user's copy of
the ISRO ICD (tools/import_navic.py) and is not in the repository, so the tests that
need it are skipped when it is absent (e.g. in CI)."""
import numpy as np
import pytest

from bdmodel import navic
from bdmodel.acquisition import acquire
from bdmodel.gps_ca import CA_LEN, ca_code
from bdmodel.signal_sim import FrontEnd
from bdmodel.signals import NAVIC_L5
from bdmodel.sim_generic import Component, generate
from bdmodel.tracking import Tracker, cn0_m2m4, symbol_phase

needs_table = pytest.mark.skipif(not navic.table_available(),
                                 reason="NavIC table not generated (tools/import_navic.py)")


def test_signal_parameters():
    assert NAVIC_L5.carrier_hz == 1176.45e6 and NAVIC_L5.chip_rate == 1.023e6
    assert NAVIC_L5.code_len == 1023 and NAVIC_L5.epoch_s == pytest.approx(1e-3)
    assert navic.EPOCHS_PER_SYMBOL * navic.SYMBOL_RATE_SPS == 1000


def test_missing_table_error_names_the_tool(monkeypatch):
    import builtins
    real = builtins.__import__

    def fake(name, *a, **k):
        if name.endswith("navic_l5_table") or (a and a[2] and "navic_l5_table" in a[2]):
            raise ImportError(name)
        return real(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", fake)
    with pytest.raises(RuntimeError, match="tools/import_navic.py"):
        navic.l5_code(1)


@needs_table
def test_table_and_gold_family():
    from bdmodel.tables.navic_l5_table import NAVIC_L5_G2_INIT
    assert sorted(NAVIC_L5_G2_INIT) == list(range(1, 15))
    allowed = {-65, -1, 63}
    f = {p: np.fft.fft(1 - 2 * navic.l5_code(p).astype(np.float64)) for p in range(1, 15)}
    for p, init in NAVIC_L5_G2_INIT.items():
        c = navic.l5_code(p)
        assert (c == 1).sum() == 512
        # G1 starts at all ones: the first 10 chips are the complement of the G2 state.
        assert "".join(str(1 - b) for b in c[:10]) == init
    for p in f:
        for q in list(f)[p:]:
            cc = np.round(np.fft.ifft(f[p] * np.conj(f[q])).real).astype(int)
            assert set(np.unique(cc)) <= allowed
        gps = np.fft.fft(1 - 2 * ca_code(1).astype(np.float64))
        assert set(np.unique(np.round(np.fft.ifft(f[p] * np.conj(gps)).real).astype(int))) <= allowed


@needs_table
def test_acquire_track_and_symbol_phase():
    fe = FrontEnd(fs_hz=16e6, f_if_hz=4.3e6)
    rng = np.random.default_rng(5)
    geo = Component(NAVIC_L5, 3, 45.0, 61.2, 300.4, 0.3, symbol_offset=9,
                    data=rng.choice([-1.0, 1.0], 40), epochs_per_symbol=navic.EPOCHS_PER_SYMBOL)
    x = generate([geo], fe, 0.6, seed=8)
    a = acquire(x, 3, fe.fs_hz, fe.f_if_hz, spec=NAVIC_L5, noncoherent=10)
    assert a.detected and abs(a.doppler_hz - geo.doppler_hz) <= 250
    assert not acquire(x, 4, fe.fs_hz, fe.f_if_hz, spec=NAVIC_L5, noncoherent=10).detected
    tr = Tracker(3, fe.fs_hz, fe.f_if_hz, a.doppler_hz, a.code_phase_chips, spec=NAVIC_L5)
    ce = []
    while tr.step(x):
        t = tr.pos / fe.fs_hz
        ce.append(((geo.chips_at(t) - tr.replica_code_chips() + CA_LEN / 2) % CA_LEN) - CA_LEN / 2)
    ce = np.array(ce[150:])
    assert abs(ce.mean()) < 0.02 and ce.std() < 0.03
    ip = np.array([r.ip for r in tr.records], dtype=np.float64)
    qp = np.array([r.qp for r in tr.records], dtype=np.float64)
    assert 43.0 < cn0_m2m4(ip[150:], qp[150:]) < 45.5
    k = symbol_phase(ip, navic.EPOCHS_PER_SYMBOL, start=150)
    assert k == geo.symbol_offset
    n0 = 150 + (-(150 + k)) % 20
    m = (len(ip) - n0) // 20
    got = np.sign(ip[n0:n0 + m * 20].reshape(m, 20).sum(axis=1))
    want = geo.data[(n0 + k) // 20:(n0 + k) // 20 + m]
    assert m >= 20 and np.mean(got == want) in (0.0, 1.0)
