"""GPS L1C codes against IS-GPS-800J (tables imported by tools/import_is800.py)."""
import numpy as np
import pytest

from bdmodel.gps_l1c import (L1C_LEN, L1C_N, OVERLAY_LEN, S2_POLY, l1c_code, l1co_overlay,
                             legendre, overlay_bits, tmboc_mask, weil_code)
from bdmodel.signals import GPS_L1CP, secondary_sync
from bdmodel.tables.gps_l1c_table import L1C_CODES, L1CO, L1CO_EXT


def _octal(bits):
    return format(int("".join(map(str, bits)), 2), "08o")


def test_legendre_definition():
    L = legendre()
    assert len(L) == L1C_N and L[0] == 0 and L[1] == 1
    assert L.sum() == (L1C_N - 1) // 2            # exactly half the non-zero residues
    # ICD 6.2.3 note: the first 23 values are 0 1 1 1 1 0 1 1 1 1 0 0 1 0 1 0 1 0 1 0 0 1 0
    assert "".join(map(str, L[:23])) == "01111011110010101010010"


@pytest.mark.parametrize("comp", ["P", "D"])
def test_codes_reproduce_table_first_and_last_24_chips(comp):
    assert sorted(L1C_CODES) == list(range(1, 211))       # 3.2-2 and 6.3-1
    for prn, row in L1C_CODES.items():
        w, p, first, last = row[comp]
        c = l1c_code(prn, comp)
        assert len(c) == L1C_LEN
        assert _octal(c[:24]) == first and _octal(c[-24:]) == last, (prn, comp)
        assert list(c[p - 1:p + 6]) == [0, 1, 1, 0, 1, 0, 0]     # expansion before the p-th chip
        assert np.array_equal(c, weil_code(w, p))


def test_prn38_errata_row():
    # IS-GPS-800J prints this row's PRN as "3"; it is the row between 37 and 39.
    assert L1C_CODES[38]["P"][:2] == (4858, 824) and L1C_CODES[3]["P"][:2] == (5108, 1)


def test_overlays_reproduce_final_11_bits():
    assert sorted(L1CO) == list(range(1, 64))
    for prn, (poly, init, final) in L1CO.items():
        s = l1co_overlay(prn)
        assert len(s) == OVERLAY_LEN
        assert "".join(map(str, s[:11])) == init and "".join(map(str, s[-11:])) == final, prn
    # ICD Table 3.2-3 note: octal 5111 is P1(x) = 1 + x^3 + x^6 + x^9 + x^11
    assert [j for j in range(12) if (L1CO[1][0] >> j) & 1] == [0, 3, 6, 9, 11]


def test_additional_overlays_reproduce_starting_and_ending_11_symbols():
    assert sorted(L1CO_EXT) == list(range(64, 211))
    for prn, (poly, s1, s2, start, end) in L1CO_EXT.items():
        s = l1co_overlay(prn)
        assert len(s) == OVERLAY_LEN
        assert "".join(map(str, s[:11])) == start and "".join(map(str, s[-11:])) == end, prn
    # IS-GPS-800J 6.3.1.2: S2 is 1 + x^9 + x^11; Table 6.3-2 note: octal 3035 is the
    # 11 values 1 1 0 0 0 0 1 1 1 0 1.
    assert [j for j in range(12) if (S2_POLY >> j) & 1] == [0, 9, 11]
    assert L1CO_EXT[64][2] == "11000011101"
    # QZSS PRN 193 as printed (Table 6.3-1 sheet 7, Table 6.3-2 sheet 7).
    assert L1C_CODES[193]["P"][:2] == (4311, 9864) and L1C_CODES[193]["D"][:2] == (4834, 9753)
    assert L1CO_EXT[193][0] == 0o5403


def test_tmboc_pattern():
    m = tmboc_mask()
    assert m.sum() == 4 * 310                        # 4 of every 33 chips, 310 groups
    assert list(np.nonzero(m)[0][:8]) == [0, 4, 6, 29, 33, 37, 39, 62]
    assert list(np.nonzero(m)[0][-4:]) == [10197, 10201, 10203, 10226]


def test_overlay_sync_on_synthetic_prompts():
    rng = np.random.default_rng(1)
    sec = 1 - 2 * np.array(l1co_overlay(24))
    k = 1234
    n = 2 * OVERLAY_LEN + 50
    prompts = 100 * sec[(np.arange(n) + k) % OVERLAY_LEN] * -1 + rng.normal(0, 30, n)  # Costas sign
    assert secondary_sync(prompts, GPS_L1CP, prn=24) == k
    assert secondary_sync(prompts, GPS_L1CP, prn=25) is None


def test_overlay_bits_rejects_nothing_silently():
    assert overlay_bits(L1CO[5][0], L1CO[5][1], 20)[:11] == [int(b) for b in L1CO[5][1]]


def test_qzss_overlay_sync_on_synthetic_prompts():
    """S1 xor S2 overlays (PRN 64-210) sync like the PRN 1-63 ones and are told apart."""
    from bdmodel.signals import QZSS_L1CP
    rng = np.random.default_rng(2)
    sec = 1 - 2 * np.array(l1co_overlay(194))
    k = 777
    n = 2 * OVERLAY_LEN + 50
    prompts = 100 * sec[(np.arange(n) + k) % OVERLAY_LEN] + rng.normal(0, 30, n)
    assert secondary_sync(prompts, QZSS_L1CP, prn=194) == k
    for other in (193, 195, 24):
        assert secondary_sync(prompts, QZSS_L1CP, prn=other) is None
