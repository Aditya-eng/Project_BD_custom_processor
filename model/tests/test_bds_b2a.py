"""BeiDou B2a codes against BDS-SIS-ICD-B2a-1.0 (imported Tables 5-2..5-4) and code properties."""
import numpy as np

from bdmodel import bds_b2a
from bdmodel.bds_b2a import (B2A_LEN, DATA_SECONDARY, b2a_code, legendre, pilot_secondary,
                             weil_truncated)
from bdmodel.tables.bds_b2a_table import B2A_CODES

# A few rows as printed in the ICD (first/last 24 chips, octal), re-checked here so the
# test does not depend on the importer having run against the PDF.
PRIMARY = {(1, "D"): ("26771056", "42646672"), (1, "P"): ("26772435", "05133452"),
           (61, "D"): ("57754771", "16642116"), (63, "D"): ("55037136", "06147764")}
SECONDARY = {1: ("32063050", "65322167"), 26: ("61576715", "07552423"),
             56: ("72744364", "62223707"), 63: ("12073317", "30264212")}


def bits(octal):
    return format(int(octal, 8), "024b")


def test_table():
    assert sorted(B2A_CODES) == list(range(1, 64))
    assert [p for p, r in B2A_CODES.items() if r["D"] != r["P"]] == [61, 62, 63]
    assert B2A_CODES[1]["S"] == (123, 138) and B2A_CODES[56]["S"] == (199, 1)


def test_printed_chips():
    for (prn, comp), (first, last) in PRIMARY.items():
        c = "".join(map(str, b2a_code(prn, comp)))
        assert len(c) == B2A_LEN and c[:24] == bits(first) and c[-24:] == bits(last), (prn, comp)
    for prn, (first, last) in SECONDARY.items():
        s = "".join(map(str, pilot_secondary(prn)))
        assert len(s) == 100 and s[:24] == bits(first) and s[-24:] == bits(last), prn


def test_legendre_is_quadratic_residues():
    L = legendre()
    qr = {(x * x) % 1021 for x in range(1, 1021)}
    assert L[0] == 0 and all(L[k] == (k in qr) for k in range(1, 1021))
    assert int(L.sum()) == 510                 # (N-1)/2 residues for prime N


def test_weil_truncation_definition():
    L = legendre()
    w, p = 7, 3
    full = [int(L[k] ^ L[(k + w) % 1021]) for k in range(1021)]
    assert list(weil_truncated(w, p)) == full[p - 1:p - 1 + 100]


def test_correlation_properties():
    def circ(a, b):
        return np.round(np.fft.ifft(np.fft.fft(a) * np.conj(np.fft.fft(b))).real)

    x = {(p, c): 1.0 - 2.0 * b2a_code(p, c) for p in (1, 2, 61) for c in "DP"}
    for v in x.values():
        auto = circ(v, v)
        assert auto[0] == B2A_LEN and np.max(np.abs(auto[1:])) < 0.05 * B2A_LEN
    keys = list(x)
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            assert np.max(np.abs(circ(x[a], x[b]))) < 0.05 * B2A_LEN, (a, b)


def test_secondary_codes():
    assert DATA_SECONDARY == (0, 0, 0, 1, 0)
    assert bds_b2a.DATA_EPOCHS_PER_SYMBOL == 5
    assert len({pilot_secondary(p) for p in range(1, 64)}) == 63
