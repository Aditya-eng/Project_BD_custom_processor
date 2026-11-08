"""GLONASS G1 (ICD L1, L2 Edition 5.1): ranging code, time mark, frequency plan, string coding."""
import numpy as np

from bdmodel import glonass as glo

# Values printed in the ICD (Table 3.1, 3.3.2.1, 3.3.2.2), re-checked without the PDF.
TABLE_3_1_L1 = {-7: 1598.0625, -1: 1601.4375, 0: 1602.0, 6: 1605.375}


def test_ranging_code():
    c = glo.ranging_code()
    assert "".join(map(str, c[:9])) == "111111100"            # 3.3.2.1
    assert len(c) == 511 and int(c.sum()) == 256              # maximal-length sequence
    v = 1.0 - 2.0 * c
    auto = np.round(np.fft.ifft(np.fft.fft(v) * np.conj(np.fft.fft(v))).real)
    assert auto[0] == 511 and set(auto[1:]) == {-1.0}         # two-valued: an m-sequence
    # The reciprocal polynomial also starts 111111100: only Fig. 3.2 separates them.
    recip = glo.fibonacci((4, 9), 9, 7, 511)
    assert "".join(map(str, recip[:9])) == "111111100" and not np.array_equal(recip, c)


def test_time_mark():
    full = glo.time_mark_from_polynomial(31)
    assert full[:30] == glo.TIME_MARK == "111110001101110101000010010110"
    assert full[30] == "0" and full.count("1") == 16          # idle 0 completes the m-sequence


def test_frequency_plan():
    for k, mhz in TABLE_3_1_L1.items():
        assert glo.carrier_hz(k) == mhz * 1e6
    # Path P2 (LO A = 1590 MHz, upper sideband): IF 12 + 0.5625 k MHz; main lobes 7.55-15.89 MHz.
    ifs = [glo.carrier_hz(k) - 1590e6 for k in glo.K_RANGE]
    assert min(ifs) - glo.CHIP_RATE > 7.5e6 and max(ifs) + glo.CHIP_RATE < 16.0e6


def test_string_round_trip_is_sign_invariant():
    rng = np.random.default_rng(4)
    info = [int(b) for b in rng.integers(0, 2, 84)]
    sym = glo.string_symbols(info)
    assert len(sym) == glo.STRING_SYMBOLS == 200
    for sign in (1.0, -1.0):
        stream = np.concatenate([np.ones(37), sign * sym, sign * glo.string_symbols([0] * 84)])
        tms = glo.find_time_marks(stream)
        assert tms[0] == 37 + 170
        assert glo.decode_string(stream, tms[0]) == info
    broken = sym.copy()
    broken[11] *= -1                                          # one meander half flipped
    assert glo.decode_string(broken, 170) is None
