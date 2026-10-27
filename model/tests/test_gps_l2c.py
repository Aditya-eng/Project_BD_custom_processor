"""GPS L2 CM / CL codes against IS-GPS-200N (imported tables) and code properties."""
import numpy as np
import pytest

from bdmodel.gps_l2c import CL_LEN, CM_LEN, MASK, POLY, l2c_code, srg
from bdmodel.tables.gps_l2c_table import L2C_CODES


def test_table_covers_all_assigned_prns():
    assert sorted(L2C_CODES) == list(range(1, 64)) + list(range(159, 211))


def test_polynomial_matches_figure_3_13():
    # 1 + X^3 + X^4 + X^5 + X^6 + X^9 + X^11 + X^13 + X^16 + X^19 + X^21 + X^24 + X^27
    exps = (0, 3, 4, 5, 6, 9, 11, 13, 16, 19, 21, 24, 27)
    assert POLY == sum(1 << e for e in exps)
    assert MASK == 0o445112474


def test_cm_end_states_all_prns():
    for prn, (cm0, _, cm_end, _) in L2C_CODES.items():
        assert srg(cm0, CM_LEN - 1)[1] == cm_end, prn


@pytest.mark.parametrize("prn", [1, 19, 37, 63, 159, 210])
def test_cl_end_states(prn):
    _, cl0, _, cl_end = L2C_CODES[prn]
    assert srg(cl0, CL_LEN - 1)[1] == cl_end


def test_code_output_is_register_lsb():
    cm0 = L2C_CODES[5][0]
    c = l2c_code(5, "M")
    assert len(c) == CM_LEN and c[0] == cm0 & 1
    chips, s = srg(cm0, 100)
    assert np.array_equal(c[:100], chips) and c[100] == s & 1
    assert len(l2c_code(5, "L")) == CL_LEN


def test_cm_correlation_properties():
    def circ(a, b):
        return np.fft.ifft(np.fft.fft(a) * np.conj(np.fft.fft(b))).real

    x = {p: 1.0 - 2.0 * l2c_code(p, "M") for p in (1, 2, 30)}
    auto = circ(x[1], x[1])
    assert auto[0] == CM_LEN
    assert np.max(np.abs(auto[1:])) < 0.05 * CM_LEN
    for a, b in ((1, 2), (1, 30), (2, 30)):
        assert np.max(np.abs(circ(x[a], x[b]))) < 0.05 * CM_LEN
