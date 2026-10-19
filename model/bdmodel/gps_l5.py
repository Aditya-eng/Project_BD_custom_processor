"""GPS L5 I5/Q5 ranging codes and Neuman-Hofman codes (IS-GPS-705J 3.2.1, 3.3.2.2, 3.3.3.1).

Each 10230-chip, 1 ms code is XA xor XB:
- XA: 13 stages, feedback 1 + x^9 + x^10 + x^12 + x^13, starts all ones and is
  reset to all ones after 8190 chips (short cycled) and at the 1 ms epoch.
- XB: 13 stages, feedback 1 + x + x^3 + x^4 + x^6 + x^7 + x^8 + x^12 + x^13,
  runs its natural 8191 chips, starts at the PRN's initial state.
Shift is from lower to higher stage; stage 13 is the output.
"""
import numpy as np

L5_LEN = 10230
L5_CHIP_RATE = 10.23e6
L5_FREQ = 1176.45e6
NH10 = np.array([0, 0, 0, 0, 1, 1, 0, 1, 0, 1], dtype=np.uint8)
NH20 = np.array([0, 0, 0, 0, 0, 1, 0, 0, 1, 1, 0, 1, 0, 1, 0, 0, 1, 1, 1, 0], dtype=np.uint8)

_XA_TAPS = (9, 10, 12, 13)
_XB_TAPS = (1, 3, 4, 6, 7, 8, 12, 13)


def _step(reg, taps):
    fb = 0
    for t in taps:
        fb ^= reg[t - 1]
    return [fb] + reg[:12]


def xb_from_advance(advance: int) -> str:
    """First 13 XB chips after advancing an all-ones XB by `advance` chips,
    in ICD notation (rightmost bit is the first out)."""
    reg = [1] * 13
    for _ in range(advance):
        reg = _step(reg, _XB_TAPS)
    out = []
    for _ in range(13):
        out.append(reg[12])
        reg = _step(reg, _XB_TAPS)
    return "".join(map(str, out))[::-1]


def xb_state_from_icd(state: str):
    """Register contents (stage 1..13) whose next 13 outputs are `state`.

    Stage 13 is output now, stage 12 next, ... so stage k holds output 13-k,
    and the ICD string is rightmost-first: register stage k = state[k-1]."""
    return [int(c) for c in state]


def l5_code(prn: int, component: str = "I") -> np.ndarray:
    """10230-chip I5 or Q5 code as uint8 logic values (0/1)."""
    from .tables.gps_l5_table import L5_CODE_PHASES   # generated; see tools/import_is705.py
    _, _, si, sq = L5_CODE_PHASES[prn]
    xb = xb_state_from_icd(si if component == "I" else sq)
    xa = [1] * 13
    out = np.empty(L5_LEN, dtype=np.uint8)
    for k in range(L5_LEN):
        if k == 8190:
            xa = [1] * 13
        out[k] = xa[12] ^ xb[12]
        xa = _step(xa, _XA_TAPS)
        xb = _step(xb, _XB_TAPS)
    return out
