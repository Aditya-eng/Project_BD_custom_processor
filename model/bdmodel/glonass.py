"""GLONASS L1 FDMA open signal (G1), ICD L1, L2 GLONASS Edition 5.1 (2008), 3.3.1-3.3.2, 4.3.3.

- FDMA: carrier f_k = 1602 MHz + k * 562.5 kHz, k = -7..+6 (Table 3.1). Every satellite
  sends the same ranging code; the frequency number k tells them apart. On this receiver's
  frequency plan (path P2, LO A = 1590 MHz, upper sideband) IF_k = 12 MHz + k * 562.5 kHz.
- Ranging code: 511-chip m-sequence at 511 kchip/s (1 ms). 9-stage register, G(X) = 1 +
  X^5 + X^9 (Fig. 3.2: stages 5 and 9 feed back into stage 1, shift 1 -> 9), all ones at
  the start of each period, output taken at stage 7. The first chips are 111111100 (3.3.2.1).
- Navigation data: 2 s strings = 85 data bits in 1.7 s, then a 30-symbol time mark in 0.3 s.
  Data bits (20 ms) are in relative (differential) code and modulo-2 added to a 100 Hz
  meander (10 ms symbols), so each bit is sent as two opposite 10 ms symbols. The time mark
  is 111110001101110101000010010110 (10 ms per symbol, no meander), the first 30 chips of the
  m-sequence of g(x) = 1 + x^3 + x^5 from all ones; each string's first data bit (an idle 0)
  completes the 31-chip period. Bit, meander, time-mark and code boundaries coincide.
- Receiver side here: symbol sync, meander pairing, time-mark search and relative decoding,
  all invariant to the Costas sign ambiguity. Hamming check and message fields are not done.
"""
from functools import lru_cache

import numpy as np

G1_F0 = 1602.0e6
G1_DF = 562.5e3
K_RANGE = range(-7, 7)
CODE_LEN = 511
CHIP_RATE = 511e3
SYMBOL_EPOCHS = 10                  # 10 ms meander / time-mark symbols
STRING_DATA_BITS = 85
TIME_MARK = "111110001101110101000010010110"
STRING_SYMBOLS = 2 * STRING_DATA_BITS + len(TIME_MARK)          # 200 symbols = 2 s


def carrier_hz(k: int) -> float:
    assert k in K_RANGE, k
    return G1_F0 + k * G1_DF


def fibonacci(taps, n_stages: int, out_stage: int, n: int) -> np.ndarray:
    """n outputs of an all-ones Fibonacci register: shift 1 -> n_stages, feedback into 1."""
    r = [1] * n_stages
    out = np.empty(n, dtype=np.uint8)
    for i in range(n):
        out[i] = r[out_stage - 1]
        f = 0
        for t in taps:
            f ^= r[t - 1]
        r = [f] + r[:-1]
    return out


@lru_cache(maxsize=None)
def ranging_code() -> np.ndarray:
    c = fibonacci((5, 9), 9, 7, CODE_LEN)
    c.flags.writeable = False
    return c


def time_mark_from_polynomial(n: int = 31) -> str:
    return "".join(map(str, fibonacci((3, 5), 5, 5, n)))


# ---- transmitter side (simulation) -------------------------------------------------
def relative_encode(bits):
    """b_k = a_k xor b_(k-1), b_(-1) = 0."""
    out, prev = [], 0
    for a in bits:
        prev ^= int(a)
        out.append(prev)
    return out


def string_symbols(info_bits) -> np.ndarray:
    """One 2 s string as 200 +/-1 symbols (10 ms each): idle 0 + 84 info bits, relative
    coded, each bit as two meander halves (bit, not bit), then the time mark."""
    info_bits = list(info_bits)
    assert len(info_bits) == STRING_DATA_BITS - 1
    b = relative_encode([0] + info_bits)
    sym = []
    for bit in b:
        sym += [bit, bit ^ 1]
    sym += [int(c) for c in TIME_MARK]
    return 1.0 - 2.0 * np.array(sym)


# ---- receiver side ----------------------------------------------------------------
def find_time_marks(symbols) -> list:
    """Indices where a time mark starts in a +/-1 (or soft) symbol stream, either sign."""
    tm = 1.0 - 2.0 * np.array([int(c) for c in TIME_MARK])
    s = np.sign(np.asarray(symbols, dtype=np.float64))
    n = len(tm)
    return [i for i in range(len(s) - n + 1) if abs(np.dot(s[i:i + n], tm)) == n]


def decode_string(symbols, tm_index: int):
    """84 info bits of the string that ends with the time mark at tm_index.

    Checks the meander (each bit's two symbols opposite) and undoes the relative code;
    neither depends on the overall sign. Returns None if the meander check fails."""
    start = tm_index - 2 * STRING_DATA_BITS
    if start < 0:
        return None
    s = np.sign(np.asarray(symbols[start:tm_index], dtype=np.float64)).reshape(-1, 2)
    if not np.all(s[:, 0] == -s[:, 1]):
        return None
    b = (s[:, 0] < 0).astype(np.int64)            # up to a global inversion
    return [int(x) for x in b[1:] ^ b[:-1]]
