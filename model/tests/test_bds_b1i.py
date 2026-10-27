"""BeiDou B1I codes against BDS-SIS-ICD-B1I-3.0 (imported Table 4-1) and code properties."""
import numpy as np

from bdmodel import bds_b1i
from bdmodel.bds_b1i import B1I_LEN, NH20, b1i_code, b1i_secondary, epochs_per_bit, gold, is_geo
from bdmodel.tables.bds_b1i_table import B1I_CODES


def test_table():
    assert sorted(B1I_CODES) == list(range(1, 64))
    geo = [p for p in B1I_CODES if is_geo(p)]
    assert geo == [1, 2, 3, 4, 5, 59, 60, 61, 62, 63]
    assert B1I_CODES[1][1] == (1, 3) and B1I_CODES[37][1] == (10, 11)
    assert B1I_CODES[38][1] == (1, 2, 7) and B1I_CODES[63][1] == (3, 6, 9)


def test_all_codes_balanced_and_distinct():
    seen = set()
    for prn, (_, taps) in B1I_CODES.items():
        g = gold(taps)
        assert int(g.sum()) == 1024, prn          # "balanced Gold code" (4.3)
        assert np.array_equal(b1i_code(prn), g[:B1I_LEN])
        seen.add(g.tobytes())
    assert len(seen) == 63


def test_balance_discriminates_conventions(monkeypatch):
    """Deliberately wrong readings of Figure 4-1 break the ICD's balance statement."""
    def unbalanced():
        return sum(int(gold(t).sum()) not in (1023, 1024) for _, t in B1I_CODES.values())

    monkeypatch.setattr(bds_b1i, "G2_FEEDBACK", (1, 3, 4, 7, 8, 9, 10, 11))  # reversed polynomial
    assert unbalanced() > 30
    monkeypatch.setattr(bds_b1i, "G2_FEEDBACK", (1, 2, 3, 4, 5, 8, 9, 11))
    monkeypatch.setattr(bds_b1i, "INIT", "10101010101")                      # complemented start
    assert unbalanced() > 30


def test_correlation_properties():
    def circ(a, b):
        return np.round(np.fft.ifft(np.fft.fft(a) * np.conj(np.fft.fft(b))).real)

    # Untruncated 2047-chip codes: G1/G2 must be a preferred pair, so every off-peak
    # auto- and cross-correlation is one of the three Gold values {-65, -1, 63}.
    gold3 = {-65.0, -1.0, 63.0}
    full = {p: 1.0 - 2.0 * gold(B1I_CODES[p][1]) for p in B1I_CODES}
    for p, v in full.items():
        auto = circ(v, v)
        assert auto[0] == 2047 and set(auto[1:]) <= gold3, p
    for a, b in ((1, 2), (6, 37), (38, 63), (5, 59)):
        assert set(circ(full[a], full[b])) <= gold3, (a, b)
    # Truncation by one chip (what is broadcast) breaks the three-valued property. Measured
    # over all 63 codes and all 1953 pairs: autocorrelation sidelobes up to 182, cross-
    # correlation up to 210 (-19.8 dB, vs -30 dB for the untruncated Gold code). Pinned
    # here as a regression value; it sets the near-far margin of B1I acquisition.
    x = {p: 1.0 - 2.0 * b1i_code(p) for p in B1I_CODES}
    f = {p: np.fft.fft(v) for p, v in x.items()}
    worst_auto = max(np.max(np.abs(circ(v, v)[1:])) for v in x.values())
    worst_cross = max(np.max(np.abs(np.round(np.fft.ifft(f[a] * np.conj(f[b])).real)))
                      for a in f for b in f if a < b)
    assert (worst_auto, worst_cross) == (182, 210)


def test_secondary_and_bit_rates():
    assert NH20 == (0, 0, 0, 0, 0, 1, 0, 0, 1, 1, 0, 1, 0, 1, 0, 0, 1, 1, 1, 0)
    assert b1i_secondary(6) == NH20 and b1i_secondary(3) is None
    assert epochs_per_bit(6) == 20 and epochs_per_bit(60) == 2


def test_bit_phase_on_synthetic_prompts():
    rng = np.random.default_rng(0)
    bits = rng.choice([-1.0, 1.0], 300)
    for k in (0, 1):
        n = np.arange(500)
        ip = 1000 * bits[(n + k) // 2] + rng.normal(0, 100, len(n))
        assert bds_b1i.bit_phase(ip, 2, start=7) == k
