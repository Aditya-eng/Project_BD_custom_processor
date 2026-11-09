"""Bit-exactness scenario shared by the two-clock simulation (tb/test_host_if.py) and the
hardware run on the VC709 (tools/hw_bitexact.py), so T2.4 executes exactly the program that
CI has already verified against the RTL.

A scenario is a list of operations on the host interface:
  ("w", addr, value)      register write (AXI-Lite / XDMA user BAR)
  ("play", a, b)          stream samples a..b-1 through H2C
  ("drain", n)            wait until the core's SAMPLE_CNT equals n
and the model's expected records. Retunes happen only after a drain, so the model knows the
exact sample at which they land (in normal operation they land on whatever sample is current).
"""
from dataclasses import dataclass, field

import numpy as np

from .correlator import TrackChannel, freq_to_fcw, rate_to_fcw
from .gps_ca import CA_CHIP_RATE, ca_code
from .records import RecordType, parse_stream
from .signal_sim import FrontEnd, SatSignal, generate

CH_BASE, CH_STRIDE = 0x1000, 0x40
REG = dict(CARR=0x00, CODE=0x04, SPACING=0x08, CODE_LEN=0x0C, PATH=0x10, LD_CARR=0x14,
           LD_FRAC=0x18, LD_CHIP=0x1C, CMD=0x20, WADDR=0x24, WDATA=0x28, MODE=0x2C)
G = dict(CTRL=0x00C, TIC_PERIOD=0x014, TIC_NEXT_LO=0x018, TIC_NEXT_HI=0x01C,
         SAMPLE_CNT_LO=0x030, SAMPLE_CNT_HI=0x034, STATUS=0x04C, SCRATCH=0x050)


@dataclass
class Scenario:
    paths: list                         # 4 sample arrays (signed 4-bit values)
    ops: list = field(default_factory=list)
    expected: dict = field(default_factory=dict)   # ch -> (dump tuples, meas tuples)
    n_tics: int = 0

    def samples_le16(self, a=0, b=None) -> bytes:
        """Samples a..b-1 as the H2C byte stream: one little-endian 16-bit word per sample,
        path p in bits [4p+3:4p]."""
        b = len(self.paths[0]) if b is None else b
        w = np.zeros(b - a, dtype=np.uint16)
        for p in range(4):
            w |= ((np.asarray(self.paths[p][a:b], dtype=np.int64) & 0xF) << (4 * p)).astype(np.uint16)
        return w.astype("<u2").tobytes()


def _ch_writes(ch, name, val):
    return ("w", CH_BASE + ch * CH_STRIDE + REG[name], int(val) & 0xFFFFFFFF)


def build(n=12000, seed=5, cuts=(4000, 8000), tic_next=1000, tic_period=3000,
          nch=4) -> Scenario:
    """Four channels exercising every mode (C/A on a simulated signal, BOC, TDM slot 1,
    plain short code), retuned twice mid-run, with tics. nch > 4 repeats the four set-ups
    on further channels (for the 192-channel hardware run)."""
    rng = np.random.default_rng(seed)
    fe = FrontEnd(fs_hz=4.0e6, f_if_hz=1.1e6)
    pathA = generate([SatSignal(7, 50.0, 2100.0, 100.25, 0.2)], fe, n / fe.fs_hz, seed=3)
    paths = [pathA, rng.integers(-8, 8, n), rng.integers(-3, 4, n), rng.integers(-8, 8, n)]
    base = {  # (path, code bits, carr Hz, code rate, spacing, chip0, mode)
        0: (0, ca_code(7), fe.f_if_hz + 2100.0, CA_CHIP_RATE * (1 + 2100 / 1575.42e6),
            1 << 31, 100, 0),
        1: (1, rng.integers(0, 2, 127).astype(np.uint8), 210000.0, 0.31e6, 1 << 30, 9, 1),
        2: (2, rng.integers(0, 2, 61).astype(np.uint8), -97000.0, 0.27e6, 3 << 29, 3, 0b110),
        3: (3, rng.integers(0, 2, 101).astype(np.uint8), 123456.0, 0.4e6, 12345, 5, 0),
    }
    sc = Scenario(paths)
    chans, setup = {}, {}
    for ch in range(nch):
        path, bits, fc, fr, sp, chip0, mode = base[ch % 4]
        fc += 7.0 * (ch // 4)                       # distinct copies on repeated set-ups
        setup[ch] = (path, bits, fc, fr, sp, chip0, mode)
        sc.ops += [_ch_writes(ch, "WADDR", 0)] + [_ch_writes(ch, "WDATA", b) for b in bits]
        cf, kf = freq_to_fcw(fc, fe.fs_hz), rate_to_fcw(fr, fe.fs_hz)
        for name, val in (("CODE_LEN", len(bits)), ("PATH", path), ("MODE", mode),
                          ("SPACING", sp), ("CARR", cf), ("CODE", kf), ("LD_CARR", 0),
                          ("LD_FRAC", 1 << 30), ("LD_CHIP", chip0), ("CMD", 2)):
            sc.ops.append(_ch_writes(ch, name, val))
        m = TrackChannel(bits, carr_fcw=cf, code_fcw=kf, half_spacing=sp, boc=bool(mode & 1),
                         tdm=bool(mode & 2), tdm_slot=(mode >> 2) & 1)
        m.load(0, 1 << 30, chip0)
        m.path = path
        chans[ch] = m
    sc.ops += [("w", G["TIC_PERIOD"], tic_period), ("w", G["TIC_NEXT_LO"], tic_next),
               ("w", G["TIC_NEXT_HI"], 0), ("w", G["CTRL"], 1)]

    bounds = [0, *cuts, n]
    cfg_events = []
    for i, (a, b) in enumerate(zip(bounds[:-1], bounds[1:])):
        if i > 0:
            sc.ops.append(("drain", a))
            for ch in range(nch):
                if ch % 4 not in (0, 3):
                    continue
                p, bits, fc, fr, sp, chip0, mode = setup[ch]
                cf = freq_to_fcw(fc + i * (3.0 if ch % 4 == 0 else -50.0), fe.fs_hz)
                kf = rate_to_fcw(fr * (1 + i * 1e-7), fe.fs_hz)
                sc.ops += [_ch_writes(ch, "CARR", cf), _ch_writes(ch, "CODE", kf),
                           _ch_writes(ch, "CMD", 1)]
                cfg_events.append((a, ch, cf, kf))
        sc.ops.append(("play", a, b))
    sc.ops.append(("drain", n))

    tics = list(range(tic_next, n, tic_period))
    out = {ch: ([], []) for ch in chans}
    marks = sorted({0, n, *[e[0] for e in cfg_events]})
    for a, b in zip(marks[:-1], marks[1:]):
        for e in cfg_events:
            if e[0] == a:
                chans[e[1]].carr_fcw, chans[e[1]].code_fcw = e[2], e[3]
        seg_tics = [x - a for x in tics if a <= x < b]
        for ch, m in chans.items():
            dd, mm = m.process(np.asarray(paths[m.path], dtype=np.int64)[a:b], seg_tics)
            out[ch][0].extend((d.epoch, d.ie, d.qe, d.ip, d.qp, d.il, d.ql) for d in dd)
            out[ch][1].extend((x.epoch, x.carr_phase, x.carr_cycles, x.code_frac, x.chip_idx,
                               x.sample_index) for x in mm)
    sc.expected = out
    sc.n_tics = len(tics)
    return sc


def compare(sc: Scenario, c2h: bytes) -> list:
    """Mismatches between the C2H byte stream and the model (empty list = bit-exact).
    Pad records are skipped; records of one channel and type must arrive in order."""
    got = {ch: ([], []) for ch in sc.expected}
    for r in parse_stream(c2h):
        if r["ch"] not in got:
            return [f"record for unexpected channel {r['ch']}"]
        if r["type"] == RecordType.DUMP:
            got[r["ch"]][0].append((r["epoch"], r["ie"], r["qe"], r["ip"], r["qp"], r["il"],
                                    r["ql"]))
        else:
            got[r["ch"]][1].append((r["epoch"], r["carr_phase"], r["carr_cycles"],
                                    r["code_frac"], r["chip_idx"], r["tic_cnt"]))
    errors = []
    for ch, (exp_d, exp_m) in sc.expected.items():
        for kind, e, g in (("dumps", exp_d, got[ch][0]), ("meas", exp_m, got[ch][1])):
            if e != g:
                first = next((i for i, (x, y) in enumerate(zip(e, g)) if x != y), min(len(e), len(g)))
                errors.append(f"ch{ch} {kind}: {len(g)} received, {len(e)} expected, "
                              f"first difference at #{first}")
    return errors
