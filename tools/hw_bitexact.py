#!/usr/bin/env python3
"""T2.4 hardware bit-exactness on the VC709: run the shared scenario (bdmodel.hwcheck, the
same program tb/test_host_if.py verifies in simulation) through the XDMA driver and compare
every DUMP and MEAS record with the Python model.

usage: hw_bitexact.py [--dev /dev/xdma0] [--nch 4] [--samples 12000] [--dry-run]

Needs the Xilinx XDMA Linux driver (character devices <dev>_user, <dev>_h2c_0, <dev>_c2h_0)
and a bitstream built from fpga/vc709. --dry-run builds the scenario and prints what would
be sent, without touching a device (CI runs this).

Not yet run on hardware (no board or 690T Vivado licence in the development environment).
The full T2.4 target (192 channels x 60 s at 79.5 MS/s) needs a faster model than the
NumPy one; this harness runs any length the model can afford.
"""
import argparse
import mmap
import os
import struct
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model"))
from bdmodel import hwcheck  # noqa: E402

USER_BAR_BYTES = 64 * 1024        # XDMA AXI-Lite master window (fpga/vc709/build.tcl)


class Xdma:
    def __init__(self, dev):
        self.ufd = os.open(f"{dev}_user", os.O_RDWR | os.O_SYNC)
        self.bar = mmap.mmap(self.ufd, USER_BAR_BYTES)
        self.h2c = os.open(f"{dev}_h2c_0", os.O_WRONLY)
        self.c2h = os.open(f"{dev}_c2h_0", os.O_RDONLY)
        self.rx = bytearray()
        self.stop = threading.Event()
        self.reader = threading.Thread(target=self._read_c2h, daemon=True)
        self.reader.start()

    def _read_c2h(self):
        while not self.stop.is_set():
            try:
                chunk = os.read(self.c2h, 64 * 32)   # returns at a packet end (tlast)
            except OSError:                       # driver timeout with no data: keep polling
                continue
            self.rx += chunk

    def wr(self, addr, val):
        self.bar[addr:addr + 4] = struct.pack("<I", val & 0xFFFFFFFF)

    def rd(self, addr):
        return struct.unpack("<I", self.bar[addr:addr + 4])[0]

    def sample_count(self):
        lo = self.rd(hwcheck.G["SAMPLE_CNT_LO"])               # latches _HI
        return self.rd(hwcheck.G["SAMPLE_CNT_HI"]) << 32 | lo

    def close(self):
        self.stop.set()
        self.bar.close()
        for fd in (self.ufd, self.h2c, self.c2h):
            os.close(fd)


def run(dev, sc, timeout_s=30.0):
    x = Xdma(dev)
    try:
        assert x.rd(0x000) == 0x42443031, "ID register: not a Project BD bitstream"
        for op in sc.ops:
            if op[0] == "w":
                x.wr(op[1], op[2])
            elif op[0] == "play":
                data = sc.samples_le16(op[1], op[2])
                view = memoryview(data)
                while view:
                    view = view[os.write(x.h2c, view):]
            else:                                              # ("drain", n)
                t0 = time.monotonic()
                while x.sample_count() != op[1]:
                    if time.monotonic() - t0 > timeout_s:
                        raise TimeoutError(f"core consumed {x.sample_count()} of {op[1]} samples")
                    time.sleep(0.001)
        time.sleep(0.05)                                       # > flush time of the last packet
        overrun = x.rd(hwcheck.G["STATUS"]) & 1
        return bytes(x.rx), overrun
    finally:
        x.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dev", default="/dev/xdma0")
    ap.add_argument("--nch", type=int, default=4)
    ap.add_argument("--samples", type=int, default=12000)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    n = a.samples - a.samples % 8                              # whole 128-bit H2C beats
    sc = hwcheck.build(n=n, cuts=(n // 3 // 8 * 8, 2 * n // 3 // 8 * 8), nch=a.nch)
    writes = sum(op[0] == "w" for op in sc.ops)
    n_exp = sum(len(d) + len(m) for d, m in sc.expected.values())
    print(f"scenario: {a.nch} channels, {n} samples, {writes} register writes, "
          f"{n_exp} expected records")
    if a.dry_run:
        return 0
    c2h, overrun = run(a.dev, sc)
    errors = hwcheck.compare(sc, c2h)
    if overrun:
        errors.append("collector overrun flag set")
    print("\n".join(errors) if errors else f"bit-exact: {len(c2h) // 32} records received")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
