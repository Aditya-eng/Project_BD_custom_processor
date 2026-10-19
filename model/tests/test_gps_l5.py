"""GPS L5 codes against IS-GPS-705J Tables 3-Ia/3-Ib and section 3.3.2.2."""
import numpy as np
import pytest

from bdmodel.gps_l5 import L5_LEN, NH10, NH20, l5_code, xb_from_advance
from bdmodel.tables.gps_l5_table import L5_CODE_PHASES


def _lfsr_outputs(state, taps, n):
    """Independent re-implementation: state[k] = stage k+1, output = stage 13."""
    s = list(state)
    out = []
    for _ in range(n):
        out.append(s[12])
        fb = 0
        for t in taps:
            fb ^= s[t - 1]
        s = [fb] + s[:12]
    return np.array(out, dtype=np.uint8)


def _code_from_advance(adv):
    """Build a code from the 'XB code advance' column only (never touches the state column)."""
    xb = _lfsr_outputs([1] * 13, (1, 3, 4, 6, 7, 8, 12, 13), adv + 8191)[adv:]   # one XB period
    xb = np.tile(xb, 2)[:L5_LEN]
    xa = _lfsr_outputs([1] * 13, (9, 10, 12, 13), 8190)                         # short cycled
    xa = np.concatenate([xa, xa])[:L5_LEN]
    return xa ^ xb


def test_table_covers_prn_1_to_63():
    assert sorted(L5_CODE_PHASES) == list(range(1, 64))


@pytest.mark.parametrize("prn", range(1, 64))
def test_advance_and_state_columns_agree(prn):
    ai, aq, si, sq = L5_CODE_PHASES[prn]
    assert xb_from_advance(ai) == si and xb_from_advance(aq) == sq


@pytest.mark.parametrize("prn", [1, 2, 13, 24, 37, 38, 63])
@pytest.mark.parametrize("comp", ["I", "Q"])
def test_code_from_state_equals_code_from_advance(prn, comp):
    ai, aq, si, sq = L5_CODE_PHASES[prn]
    code = l5_code(prn, comp)
    assert len(code) == L5_LEN
    assert np.array_equal(code, _code_from_advance(ai if comp == "I" else aq))
    # ICD footnote: XA starts all ones, so the first 13 code chips are the
    # complement of the XB state (written rightmost-first).
    state = si if comp == "I" else sq
    assert "".join(str(1 - b) for b in code[:13]) == state[::-1]


def test_neuman_hofman_codes_as_printed():
    assert "".join(map(str, NH10)) == "0000110101"                 # IS-GPS-705J 3.3.3.1.2
    assert " ".join(map(str, NH20)) == "0 0 0 0 0 1 0 0 1 1 0 1 0 1 0 0 1 1 1 0"   # 3.3.3.2


def test_low_cross_correlation():
    def pm(c):
        return 1.0 - 2.0 * c.astype(np.float64)
    a, b, c = pm(l5_code(1, "I")), pm(l5_code(1, "Q")), pm(l5_code(2, "I"))
    fa = np.fft.fft(a)
    for other in (b, c):
        cc = np.fft.ifft(fa * np.conj(np.fft.fft(other))).real / L5_LEN
        assert np.max(np.abs(cc)) < 0.06
    ac = np.fft.ifft(fa * np.conj(fa)).real / L5_LEN
    assert abs(ac[0] - 1) < 1e-9 and np.max(np.abs(ac[1:])) < 0.06
