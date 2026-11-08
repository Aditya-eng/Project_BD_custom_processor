"""BeiDou B1C codes against BDS-SIS-ICD-B1C-1.0 (imported Tables 5-2..5-4) and code properties."""
import numpy as np

from bdmodel import weil
from bdmodel.bds_b1c import B1C_LEN, SECONDARY_LEN, b1c_code, pilot_secondary
from bdmodel.signals import BDS_B1C_P, secondary_sync
from bdmodel.tables.bds_b1c_table import B1C_CODES

# Rows as printed (first/last 24 chips, octal), re-checked without the PDF.
PRIMARY = {(1, "D"): ("53773116", "42711657"), (5, "D"): ("17205134", "46341377"),
           (63, "P"): ("03210227", "56250500")}
SECONDARY = {1: ("27516364", "67377026"), 6: ("17464233", "72132153"),
             63: ("24724407", "27051216")}


def bits(octal):
    return format(int(octal, 8), "024b")


def test_table_and_icd_example():
    assert sorted(B1C_CODES) == list(range(1, 64))
    # 5.2.1: "the first 24 chips of the B1C data component primary code of PRN 1 are
    # 101011111111011001001110 in binary, or equivalently, 53773116 in octal".
    assert "".join(map(str, b1c_code(1, "D")[:24])) == "101011111111011001001110"


def test_printed_chips():
    for (prn, comp), (first, last) in PRIMARY.items():
        c = "".join(map(str, b1c_code(prn, comp)))
        assert len(c) == B1C_LEN and c[:24] == bits(first) and c[-24:] == bits(last), (prn, comp)
    for prn, (first, last) in SECONDARY.items():
        s = "".join(map(str, pilot_secondary(prn)))
        assert len(s) == SECONDARY_LEN and s[:24] == bits(first) and s[-24:] == bits(last), prn


def test_legendre_lengths_are_prime_residue_sets():
    for n in (10243, 3607):
        assert all(n % d for d in range(2, int(n ** 0.5) + 1))
        assert int(weil.legendre(n).sum()) == (n - 1) // 2


def test_correlation_properties():
    def circ(a, b):
        return np.round(np.fft.ifft(np.fft.fft(a) * np.conj(np.fft.fft(b))).real)

    x = {(p, c): 1.0 - 2.0 * b1c_code(p, c) for p in (1, 2, 40) for c in "DP"}
    for v in x.values():
        auto = circ(v, v)
        assert auto[0] == B1C_LEN and np.max(np.abs(auto[1:])) < 0.05 * B1C_LEN
    keys = list(x)
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            assert np.max(np.abs(circ(x[a], x[b]))) < 0.05 * B1C_LEN, (a, b)


def test_secondary_sync_on_synthetic_prompts():
    """18 s secondary codes are too long for a CI signal run; sync on synthetic prompts."""
    rng = np.random.default_rng(2)
    sec = 1 - 2 * np.array(pilot_secondary(17))
    k = 777
    n = 2 * SECONDARY_LEN + 40
    prompts = -100 * sec[(np.arange(n) + k) % SECONDARY_LEN] + rng.normal(0, 30, n)
    assert secondary_sync(prompts, BDS_B1C_P, prn=17) == k
    assert secondary_sync(prompts, BDS_B1C_P, prn=18) is None
