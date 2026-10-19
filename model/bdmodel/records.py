"""Record format of the FPGA collector stream (docs/REGISTERS.md §3).

Each record is 256 bits = 8 little-endian 32-bit words. Word 0:
[31:28] type, [27:16] channel, [15:0] epoch counter.
"""
from enum import IntEnum

import numpy as np

RECORD_BYTES = 32


class RecordType(IntEnum):
    DUMP = 1
    MEAS = 2


def _s32(v: int) -> int:
    return v - (1 << 32) if v & (1 << 31) else v


def parse_words(w) -> dict:
    rtype = RecordType(w[0] >> 28)
    rec = {"type": rtype, "ch": (w[0] >> 16) & 0xFFF, "epoch": w[0] & 0xFFFF}
    if rtype == RecordType.DUMP:
        for i, name in enumerate(("ie", "qe", "ip", "qp", "il", "ql")):
            rec[name] = _s32(w[1 + i])
    else:
        rec.update(carr_phase=w[1], carr_cycles=_s32(w[2]), code_frac=w[3], chip_idx=w[4],
                   tic_cnt=w[5] | (w[6] << 32))
    return rec


def parse_record(value: int) -> dict:
    """Parse one record given as a 256-bit integer (word 0 in the LSBs)."""
    return parse_words([(value >> (32 * i)) & 0xFFFFFFFF for i in range(8)])


def parse_stream(buf: bytes):
    """Parse a byte stream of back-to-back records as DMA delivers them."""
    w = np.frombuffer(buf, dtype="<u4").reshape(-1, 8)
    return [parse_words([int(x) for x in row]) for row in w]


def pack_dump(ch: int, d) -> bytes:
    """Encode a model Dump as the FPGA would (used for host-software tests)."""
    w = [(RecordType.DUMP << 28) | (ch << 16) | (d.epoch & 0xFFFF)]
    w += [v & 0xFFFFFFFF for v in (d.ie, d.qe, d.ip, d.qp, d.il, d.ql)] + [0]
    return np.array(w, dtype="<u4").tobytes()
