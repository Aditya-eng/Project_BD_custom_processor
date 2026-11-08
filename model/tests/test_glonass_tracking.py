"""GLONASS G1: FDMA acquisition/tracking of satellites sharing one code on adjacent and distant
frequency numbers, and string decoding (meander, time mark, relative code) from tracked prompts."""
import numpy as np
import pytest

from bdmodel import glonass as glo
from bdmodel.acquisition import acquire
from bdmodel.signal_sim import FrontEnd
from bdmodel.signals import glonass_g1
from bdmodel.sim_generic import Component, generate
from bdmodel.tracking import Tracker, cn0_m2m4, symbol_phase

HALF = glo.CODE_LEN / 2


def _err(a, b):
    return ((a - b + HALF) % glo.CODE_LEN) - HALF


@pytest.fixture(scope="module")
def fdma():
    # Path P2 as planned: IF_k = 12 MHz + k * 562.5 kHz; fs above twice the top of the band.
    fe = FrontEnd(fs_hz=40e6, f_if_hz=12.0e6)
    sats = {0: Component(glonass_g1(0), 0, 46.0, 1234.5, 100.3, 0.1, if_offset_hz=0.0),
            1: Component(glonass_g1(1), 1, 44.0, -2876.0, 377.8, 0.6, if_offset_hz=glo.G1_DF),
            -7: Component(glonass_g1(-7), -7, 45.0, 3321.0, 250.1, 0.3,
                          if_offset_hz=-7 * glo.G1_DF)}
    return fe, sats, generate(list(sats.values()), fe, 0.3)


def test_fdma_channels(fdma):
    fe, sats, x = fdma
    for k, c in sats.items():
        f_if = fe.f_if_hz + c.if_offset_hz
        a = acquire(x, k, fe.fs_hz, f_if, spec=c.spec, noncoherent=8)
        assert a.detected and abs(a.doppler_hz - c.doppler_hz) <= 250, k
        assert abs(_err(a.code_phase_chips, c.code_phase_chips)) < 0.5, k
        tr = Tracker(k, fe.fs_hz, f_if, a.doppler_hz, a.code_phase_chips, spec=c.spec)
        ce = []
        while tr.step(x):
            ce.append(_err(c.chips_at(tr.pos / fe.fs_hz), tr.replica_code_chips()))
        ce = np.array(ce[150:])
        assert abs(ce.mean()) < 0.02 and ce.std() < 0.02, k            # 1 chip = 587 m
        ip = [r.ip for r in tr.records][150:]
        qp = [r.qp for r in tr.records][150:]
        assert c.cn0_dbhz - 2.5 < cn0_m2m4(ip, qp) < c.cn0_dbhz + 0.5, k
    # Same code, but nothing transmits on k = +2: the adjacent k = +1 satellite (562.5 kHz
    # away) must not show up in a +/-5 kHz search there.
    a = acquire(x, 2, fe.fs_hz, fe.f_if_hz + 2 * glo.G1_DF, spec=glonass_g1(2), noncoherent=8)
    assert not a.detected


def test_string_decoding():
    fe = FrontEnd(fs_hz=8e6, f_if_hz=2.1e6)
    rng = np.random.default_rng(7)
    strings = [[int(b) for b in rng.integers(0, 2, 84)] for _ in range(2)]
    symbols = np.concatenate([glo.string_symbols(s) for s in strings])
    start = 1373                                   # epochs into the stream at t = 0 (mid-symbol)
    c = Component(glonass_g1(-2), -2, 45.0, 812.0, 33.4, 0.25, data=symbols,
                  epochs_per_symbol=glo.SYMBOL_EPOCHS, symbol_offset=start)
    x = generate([c], fe, 2.7, seed=5)
    tr = Tracker(-2, fe.fs_hz, fe.f_if_hz, 812.0 + 15.0, 33.4 + 0.2, spec=c.spec)
    tr.run(x)
    ip = np.array([r.ip for r in tr.records], dtype=np.float64)
    S = 200
    k = symbol_phase(ip, glo.SYMBOL_EPOCHS, start=S)
    assert k == start % glo.SYMBOL_EPOCHS
    n0 = S + (-(S + k)) % glo.SYMBOL_EPOCHS
    m = (len(ip) - n0) // glo.SYMBOL_EPOCHS
    soft = ip[n0:n0 + m * glo.SYMBOL_EPOCHS].reshape(m, glo.SYMBOL_EPOCHS).sum(axis=1)
    tms = glo.find_time_marks(soft)
    # Record r is stream epoch r + start, so soft[j] is stream symbol (n0 + start) / 10 + j.
    # Both strings end with a mark (symbols 170 and 370); only the second is complete in the run.
    first = (n0 + start) // glo.SYMBOL_EPOCHS
    assert [first + t for t in tms] == [170, 370]
    assert glo.decode_string(soft, tms[0]) is None
    assert glo.decode_string(soft, tms[1]) == strings[1]
