import numpy as np
import pytest

from bdmodel.gps_ca import CA_LEN, ca_code, first10_octal

# IS-GPS-200 Table 3-Ia, "First 10 Chips C/A" (octal).
IS_GPS_200_FIRST10 = {1: "1440", 2: "1620", 3: "1710", 4: "1744", 5: "1133",
                      6: "1455", 7: "1131", 8: "1454", 9: "1626", 10: "1504"}


@pytest.mark.parametrize("prn,octal", IS_GPS_200_FIRST10.items())
def test_first_10_chips_match_icd(prn, octal):
    assert first10_octal(prn) == octal


@pytest.mark.parametrize("prn", range(1, 33))
def test_gold_code_balance_and_autocorrelation(prn):
    c = 1 - 2 * ca_code(prn).astype(np.int64)
    assert (c == -1).sum() == 512          # 512 ones, 511 zeros
    ac = np.array([np.dot(c, np.roll(c, k)) for k in range(1, CA_LEN)])
    assert set(np.unique(ac)) <= {-65, -1, 63}


def test_cross_correlation_bounded():
    a = 1 - 2 * ca_code(1).astype(np.int64)
    b = 1 - 2 * ca_code(2).astype(np.int64)
    cc = np.real(np.fft.ifft(np.fft.fft(a) * np.conj(np.fft.fft(b))))
    assert np.max(np.abs(np.round(cc))) <= 65


# ---- PRN 64-210 (IS-GPS-200N Table 6-I: SBAS 120-158, QZSS 193-202) ----
from bdmodel.gps_ca import ca_code_from_delay, ca_code_from_g2_init  # noqa: E402
from bdmodel.tables.gps_ca_ext_table import CA_EXT  # noqa: E402

# Read off the PDF independently of the importer: Table 6-I sheet 1 PRN 64 and the
# footnote's spelled-out first 10 chips; sheet 3 PRN 120 (first SBAS code).
TABLE_6_I = {64: (729, "0254", "1523"), 120: (145, "1106", "0671")}


def test_table_6_i_covers_64_to_210():
    assert sorted(CA_EXT) == list(range(64, 211))
    for prn, row in TABLE_6_I.items():
        assert CA_EXT[prn] == row
    assert "".join(map(str, ca_code(64)[:10])) == "1101010011"


def test_delay_method_reproduces_table_3_ia_tap_codes():
    """The G2 delay convention (G1 xor G2 rolled by d) reproduces the two-tap codes of
    PRN 1-32 at the delays printed in Table 3-Ia (5, 6, 7, 8, 17, 18, 139, ...)."""
    delays = [5, 6, 7, 8, 17, 18, 139, 140, 141, 251, 252, 254, 255, 256, 257, 258,
              469, 470, 471, 472, 473, 474, 509, 512, 513, 514, 515, 516, 859, 860, 861, 862]
    for prn, d in zip(range(1, 33), delays):
        assert np.array_equal(ca_code_from_delay(d), ca_code(prn)), prn


@pytest.mark.parametrize("prn", range(64, 211))
def test_extension_rows_self_consistent(prn):
    delay, init, first10 = CA_EXT[prn]
    c = ca_code(prn)
    assert first10_octal(prn).zfill(4) == first10
    bits = [int(init[0])] + [int(b) for b in format(int(init[1:], 8), "09b")]
    assert np.array_equal(ca_code_from_g2_init(bits), c)
    assert (c == 1).sum() == 512                      # balanced Gold code


def test_extension_codes_are_gold_family():
    """Every extension code shares the GPS Gold family: three-valued cross-correlation
    {-65, -1, 63} with the GPS codes and with each other (sample of pairs)."""
    def f(prn):
        return np.fft.fft(1 - 2 * ca_code(prn).astype(np.float64))
    gps = [f(p) for p in (1, 7, 19, 32)]
    ext = [f(p) for p in (64, 120, 123, 136, 158, 193, 199, 202, 210)]
    allowed = {-65, -1, 63}
    for i, a in enumerate(ext):
        for b in gps + ext[i + 1:]:
            cc = np.round(np.fft.ifft(a * np.conj(b)).real).astype(int)
            assert set(np.unique(cc)) <= allowed
        ac = np.round(np.fft.ifft(a * np.conj(a)).real).astype(int)
        assert ac[0] == CA_LEN and set(np.unique(ac[1:])) <= allowed
