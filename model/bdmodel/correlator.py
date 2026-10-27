"""Bit-exact model of rtl/track_channel.sv.

Every arithmetic step here is the contract the RTL must match exactly
(see docs/ARCHITECTURE.md, "Tracking channel contract").

Per accepted sample, using the channel state *before* the update:
  lut_idx   = carr_phase[31:27]
  I         = s * COS_LUT[lut_idx]
  Q         = -s * SIN_LUT[lut_idx]
  early chip = chip + carry(code_frac + D)          (mod code_len)
  late chip  = chip - (code_frac < D)               (mod code_len)
  tap value  = code bit of the tap's chip, XOR (BOC(1,1) mode only) bit 31 of
               the tap's fractional phase: frac+D (E), frac (P), frac-D (L), mod 2^32
  each accumulator += sign(tap value) * (I or Q)
  TDM mode: a tap whose fractional-phase bit 31 differs from tdm_slot adds 0
  (time-multiplexed codes such as GPS L2 CM/CL: one code per half chip)
then the state advances:
  carr_phase += carr_fcw (signed, mod 2^32); carr_cycles += wrap direction
  code_frac  += code_fcw (unsigned, mod 2^32); chip += carry (mod code_len)
If the chip wrapped from code_len-1 to 0, the accumulators (including this
sample) are dumped and cleared, and epoch_cnt increments.
"""
from dataclasses import dataclass, field

import numpy as np

M32 = (1 << 32) - 1
LUT_BITS = 5
LUT_AMP = 15
_k = np.arange(1 << LUT_BITS)
COS_LUT = np.round(LUT_AMP * np.cos(2 * np.pi * (_k + 0.5) / (1 << LUT_BITS))).astype(np.int64)
SIN_LUT = np.round(LUT_AMP * np.sin(2 * np.pi * (_k + 0.5) / (1 << LUT_BITS))).astype(np.int64)


def wrap_s32(x: int) -> int:
    x &= M32
    return x - (1 << 32) if x & (1 << 31) else x


def freq_to_fcw(freq_hz: float, fs_hz: float) -> int:
    """Signed 32-bit carrier frequency control word."""
    return wrap_s32(int(round(freq_hz / fs_hz * (1 << 32))))


def rate_to_fcw(rate_hz: float, fs_hz: float) -> int:
    """Unsigned 32-bit code-rate control word (chips per sample * 2^32)."""
    v = int(round(rate_hz / fs_hz * (1 << 32)))
    assert 0 <= v < (1 << 31), "code rate must be below fs/2"
    return v


@dataclass
class Dump:
    sample_index: int      # absolute index of the last sample in the epoch
    epoch: int             # epoch_cnt value after the dump
    ie: int
    qe: int
    ip: int
    qp: int
    il: int
    ql: int


@dataclass
class Meas:
    sample_index: int
    carr_phase: int
    carr_cycles: int
    code_frac: int
    chip_idx: int
    epoch: int


@dataclass
class TrackChannel:
    code_bits: np.ndarray
    carr_fcw: int = 0
    code_fcw: int = 0
    half_spacing: int = 1 << 31   # D, in chips * 2^32 (0.5 chip default)
    carr_phase: int = 0
    carr_cycles: int = 0
    code_frac: int = 0
    chip_idx: int = 0
    epoch_cnt: int = 0
    sample_count: int = 0
    boc: bool = False                 # sine-phased BOC(1,1) subcarrier on the replica
    tdm: bool = False                 # replica present in one half of each chip only
    tdm_slot: int = 0                 # that half: 0 first, 1 second
    acc: np.ndarray = field(default_factory=lambda: np.zeros(6, dtype=np.int64))

    def __post_init__(self):
        self.code_bits = np.asarray(self.code_bits, dtype=np.uint8)
        self.code_len = len(self.code_bits)
        self._sign = 1 - 2 * self.code_bits.astype(np.int64)

    def load(self, carr_phase=0, code_frac=0, chip_idx=0):
        self.carr_phase = carr_phase & M32
        self.carr_cycles = 0
        self.code_frac = code_frac & M32
        self.chip_idx = chip_idx
        self.epoch_cnt = 0
        self.acc[:] = 0

    def process(self, samples, tics=()):
        """Consume `samples` with the current control words.

        `tics` holds indices (relative to this block) where the measurement
        latch fires. Returns (dumps, measurements).
        """
        s = np.asarray(samples, dtype=np.int64)
        n_s = len(s)
        if n_s == 0:
            return [], []
        L = self.code_len
        n = np.arange(n_s, dtype=np.int64)
        n1 = n + 1

        carr_tot = self.carr_phase + n * self.carr_fcw
        cp = carr_tot & M32
        cyc = self.carr_cycles + (carr_tot >> 32)
        idx = cp >> (32 - LUT_BITS)
        i_val = s * COS_LUT[idx]
        q_val = -s * SIN_LUT[idx]

        code_tot = self.code_frac + n * self.code_fcw
        frac = code_tot & M32
        chip_abs = self.chip_idx + (code_tot >> 32)
        p_idx = chip_abs % L
        e_idx = (chip_abs + ((frac + self.half_spacing) >> 32)) % L
        l_idx = (chip_abs - (frac < self.half_spacing).astype(np.int64)) % L
        e_s = self._sign[e_idx]
        p_s = self._sign[p_idx]
        l_s = self._sign[l_idx]
        if self.boc:
            e_s = e_s * (1 - 2 * (((frac + self.half_spacing) & M32) >> 31))
            p_s = p_s * (1 - 2 * (frac >> 31))
            l_s = l_s * (1 - 2 * (((frac - self.half_spacing) & M32) >> 31))
        if self.tdm:
            e_s = e_s * ((((frac + self.half_spacing) & M32) >> 31) == self.tdm_slot)
            p_s = p_s * ((frac >> 31) == self.tdm_slot)
            l_s = l_s * ((((frac - self.half_spacing) & M32) >> 31) == self.tdm_slot)
        epoch_of = chip_abs // L
        chip_abs_next = self.chip_idx + ((self.code_frac + n1 * self.code_fcw) >> 32)
        is_last = (chip_abs_next // L) > epoch_of

        prods = np.stack([e_s * i_val, e_s * q_val, p_s * i_val, p_s * q_val,
                          l_s * i_val, l_s * q_val])

        meas = []
        for k in tics:
            meas.append(Meas(self.sample_count + k, int(cp[k]), wrap_s32(int(cyc[k])),
                             int(frac[k]), int(p_idx[k]), (self.epoch_cnt + int(epoch_of[k])) & 0xFFFF))

        dumps = []
        start = 0
        for end in np.nonzero(is_last)[0]:
            tot = self.acc + prods[:, start:end + 1].sum(axis=1)
            self.acc[:] = 0
            ep = (self.epoch_cnt + int(epoch_of[end]) + 1) & 0xFFFF
            dumps.append(Dump(self.sample_count + int(end), ep, *[wrap_s32(int(v)) for v in tot]))
            start = end + 1
        self.acc += prods[:, start:].sum(axis=1)

        last_tot = self.carr_phase + n_s * self.carr_fcw
        self.carr_cycles = wrap_s32(self.carr_cycles + (last_tot >> 32))
        self.carr_phase = last_tot & M32
        last_code = self.code_frac + n_s * self.code_fcw
        chip_end = self.chip_idx + (last_code >> 32)
        self.epoch_cnt = (self.epoch_cnt + chip_end // L) & 0xFFFF
        self.chip_idx = chip_end % L
        self.code_frac = last_code & M32
        self.sample_count += n_s
        return dumps, meas

    def samples_to_epoch_end(self) -> int:
        """Number of samples until (and including) the next dump."""
        remaining_chips = self.code_len - self.chip_idx
        need = (remaining_chips << 32) - self.code_frac
        return -(-need // self.code_fcw)

    def code_phase_chips(self) -> float:
        return self.chip_idx + self.code_frac / 2**32
