"""Galileo codes against the OS SIS ICD (tables imported by tools/import_galileo_icd.py)."""
import hashlib

import numpy as np
import pytest

from bdmodel.galileo import E1_LEN, E5_LEN, e1_code, e5_code, hex_to_bits, lfsr_code, secondary
from bdmodel.tables.galileo_tables import E5_PARAMS, E5_SHA256, SECONDARY


def test_hex_convention_matches_table_107():
    # ICD Table 107: chips 1110110001 (+ two zero fills) -> "EC4"
    assert "".join(map(str, hex_to_bits("EC4"))) == "111011000100"


@pytest.mark.parametrize("comp", ["E5aI", "E5aQ", "E5bI", "E5bQ"])
def test_e5_lfsr_reproduces_every_attached_code(comp):
    """SHA-256 of each code in the ICD's electronic Annex C, recorded at import."""
    t1, t2, starts = E5_PARAMS[comp]
    assert sorted(starts) == list(range(1, 51))
    for prn, s2 in starts.items():
        code = lfsr_code(t1, t2, s2)
        assert len(code) == E5_LEN
        assert hashlib.sha256(bytes(code)).hexdigest() == E5_SHA256[(comp, prn)], (comp, prn)


def test_e5_component_accessor():
    assert np.array_equal(e5_code(1, "aI"), lfsr_code(*E5_PARAMS["E5aI"][:2], E5_PARAMS["E5aI"][2][1]))
    # ICD Table 17, code 1: first 24 chips 3CEA9D
    assert "%06X" % int("".join(map(str, e5_code(1, "aI")[:24])), 2) == "3CEA9D"


def _pm(c):
    return 1.0 - 2.0 * c.astype(np.float64)


@pytest.mark.parametrize("comp", ["B", "C"])
def test_e1_memory_codes(comp):
    codes = [e1_code(p, comp) for p in range(1, 51)]
    assert all(len(c) == E1_LEN for c in codes)
    assert len({c.tobytes() for c in codes}) == 50
    # Optimised codes: periodic auto- and cross-correlation sidelobes stay small.
    f = [np.fft.fft(_pm(c)) for c in codes[:6]]
    for i, fi in enumerate(f):
        ac = np.fft.ifft(fi * np.conj(fi)).real / E1_LEN
        assert abs(ac[0] - 1) < 1e-9 and np.max(np.abs(ac[1:])) < 0.08
        for fj in f[i + 1:]:
            assert np.max(np.abs(np.fft.ifft(fi * np.conj(fj)).real / E1_LEN)) < 0.08


def test_e1b_and_e1c_differ_and_decorrelate():
    b, c = _pm(e1_code(7, "B")), _pm(e1_code(7, "C"))
    cc = np.fft.ifft(np.fft.fft(b) * np.conj(np.fft.fft(c))).real / E1_LEN
    assert np.max(np.abs(cc)) < 0.08


def test_secondary_codes():
    # Section 3.5.1 prints CS25 in binary; Table 22 gives CS4, CS20.
    assert "".join(map(str, secondary(25))) == "0011100000001010110110010"
    assert "".join(map(str, secondary(4))) == "1110"
    assert "".join(map(str, secondary(20))) == "10000100001011101001"
    assert sorted(k for k in SECONDARY if k[0] == 100) == [(100, i) for i in range(1, 101)]
    assert len({SECONDARY[(100, i)] for i in range(1, 101)}) == 100
