"""GPS L1 C/A Gold code generator (IS-GPS-200, Table 3-Ia).

Chip convention used throughout Project BD: logic 0 -> +1, logic 1 -> -1.
"""
import numpy as np

CA_LEN = 1023
CA_CHIP_RATE = 1.023e6
L1_FREQ = 1575.42e6

# G2 phase-selector tap pairs (1-based stage numbers) for PRN 1..32.
G2_TAPS = {
    1: (2, 6), 2: (3, 7), 3: (4, 8), 4: (5, 9), 5: (1, 9), 6: (2, 10), 7: (1, 8),
    8: (2, 9), 9: (3, 10), 10: (2, 3), 11: (3, 4), 12: (5, 6), 13: (6, 7),
    14: (7, 8), 15: (8, 9), 16: (9, 10), 17: (1, 4), 18: (2, 5), 19: (3, 6),
    20: (4, 7), 21: (5, 8), 22: (6, 9), 23: (1, 3), 24: (4, 6), 25: (5, 7),
    26: (6, 8), 27: (7, 9), 28: (8, 10), 29: (1, 6), 30: (2, 7), 31: (3, 8),
    32: (4, 9),
}


def ca_code(prn: int) -> np.ndarray:
    """Return the 1023-chip C/A code for `prn` as uint8 logic values (0/1)."""
    t1, t2 = G2_TAPS[prn]
    g1 = [1] * 10
    g2 = [1] * 10
    out = np.empty(CA_LEN, dtype=np.uint8)
    for i in range(CA_LEN):
        out[i] = g1[9] ^ g2[t1 - 1] ^ g2[t2 - 1]
        f1 = g1[2] ^ g1[9]
        f2 = g2[1] ^ g2[2] ^ g2[5] ^ g2[7] ^ g2[8] ^ g2[9]
        g1 = [f1] + g1[:9]
        g2 = [f2] + g2[:9]
    return out


def first10_octal(prn: int) -> str:
    """First 10 chips in the octal notation used by IS-GPS-200."""
    bits = ca_code(prn)[:10]
    return format(int("".join(str(b) for b in bits), 2), "o")


def bits_to_pm1(bits: np.ndarray) -> np.ndarray:
    return 1 - 2 * bits.astype(np.int8)
