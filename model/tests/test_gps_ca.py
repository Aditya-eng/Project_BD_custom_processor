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
