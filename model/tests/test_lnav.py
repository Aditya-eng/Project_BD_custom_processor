import numpy as np
import pytest

from bdmodel.ephemeris import Ephemeris
from bdmodel.lnav import (PREAMBLE, check_word, decode_subframe, decode_tlm_how, encode_subframe,
                          encode_word, ephemeris_from_subframes, find_subframe_start, quantize)
from bdmodel.scenario import make_constellation


def _eph():
    return Ephemeris(prn=5, week=2400, toc=360000.0, af0=-1.2345e-4, af1=3.1e-12, af2=0.0,
                     tgd=-5.1e-9, iodc=77, iode=77, toe=360000.0, sqrt_a=5153.71, e=0.0123,
                     m0=1.234, delta_n=4.6e-9, omega0=-2.1, i0=0.96, omega=0.7,
                     omega_dot=-8.1e-9, idot=-2.3e-10, cuc=-1.1e-6, cus=6.2e-6, crc=231.5,
                     crs=-17.3, cic=4.4e-8, cis=-3.3e-8)


@pytest.mark.parametrize("seed", range(20))
def test_word_parity_roundtrip_and_single_bit_errors(seed):
    rng = np.random.default_rng(seed)
    d = list(rng.integers(0, 2, 24))
    d29s, d30s = int(rng.integers(0, 2)), int(rng.integers(0, 2))
    w = encode_word(d, d29s, d30s)
    ok, back = check_word(w, d29s, d30s)
    assert ok and back == d
    for k in range(30):            # every single-bit error is detected (Hamming distance 4)
        w2 = list(w)
        w2[k] ^= 1
        assert not check_word(w2, d29s, d30s)[0]


@pytest.mark.parametrize("sf_id", [1, 2, 3, 4, 5])
def test_subframe_structure(sf_id):
    bits = encode_subframe(sf_id, 12345, _eph())
    assert len(bits) == 300 and bits[:8] == PREAMBLE
    # Words 2 and 10 end in 00, so every TLM is sent with D30* = 0 (upright preamble).
    assert bits[58:60] == [0, 0] and bits[298:300] == [0, 0]
    sf = decode_subframe(bits)
    assert sf["ok"] and sf["tow_count"] == 12345 and sf["sf_id"] == sf_id
    assert decode_tlm_how(bits) == (True, 12345, sf_id)


def test_ephemeris_roundtrip_within_lsb():
    eph = _eph()
    sfs = [decode_subframe(encode_subframe(k, 1, eph)) for k in (1, 2, 3)]
    q = ephemeris_from_subframes(*sfs, prn=5)
    lsb = {"af0": 2**-31, "af1": 2**-43, "tgd": 2**-31, "sqrt_a": 2**-19, "e": 2**-33,
           "m0": 2**-31 * np.pi, "omega0": 2**-31 * np.pi, "i0": 2**-31 * np.pi,
           "omega": 2**-31 * np.pi, "delta_n": 2**-43 * np.pi, "omega_dot": 2**-43 * np.pi,
           "idot": 2**-43 * np.pi, "crc": 2**-5, "crs": 2**-5, "cuc": 2**-29, "cus": 2**-29,
           "cic": 2**-29, "cis": 2**-29}
    for name, l in lsb.items():
        assert abs(getattr(q, name) - getattr(eph, name)) <= 0.5 * l + 1e-15, name
    assert (q.toe, q.toc, q.iode, q.iodc, q.week) == (eph.toe, eph.toc, eph.iode, eph.iodc, 2400 % 1024)
    assert quantize(q).__dict__ == {**q.__dict__, "week": q.week}   # idempotent


def test_find_subframe_in_inverted_stream():
    rng = np.random.default_rng(3)
    eph = make_constellation()[0]
    stream = list(rng.integers(0, 2, 137)) + encode_subframe(2, 60001, eph) + encode_subframe(3, 60002, eph)
    inv = [1 - b for b in stream]
    assert find_subframe_start(stream)[:4] == (137, False, 60001, 2)
    assert find_subframe_start(inv)[:4] == (137, True, 60001, 2)
