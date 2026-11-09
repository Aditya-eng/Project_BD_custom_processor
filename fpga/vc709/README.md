# Project BD on the Xilinx VC709 (M2)

**Status:** the PCIe host interface behind this build (`rtl/bd_host_if.sv`) is verified bit-exact in a two-clock simulation (TEST_PLAN T0.21). The files in this directory have **not yet been run through Vivado or loaded on a board**: the development environment has neither. Expect a few edits on the first build (docs/RISKS.md R15).

## What the bitstream contains

| Block | Setting |
|---|---|
| Device | XC7VX690T-2FFG1761 (VC709) |
| PCIe | XDMA IP, Gen2 x8, AXI-Stream 128 bit at 250 MHz: one H2C channel (sample playback), one C2H channel (records), 64 KB AXI-Lite user BAR (registers) |
| Core | `bd_host_if` → `bd_core`, `NCH` channels (default 192), code memory 16384 chips per channel |
| Sample clock | 79.5 MHz from an MMCM on the 200 MHz board oscillator (exact: 200 × 19.875 / 5 / 10) |
| Front end | none yet: the live inputs are tied off; samples come from the host (CTRL bit 0 = 1) |
| LEDs | 0: MMCM locked · 1: PCIe clock heartbeat while the link is up · 2: sample clock heartbeat · 3: PPS output |

Pins (`vc709.xdc`) are copied from the Xilinx board definition (XilinxBoardStore 2023.2, `boards/Xilinx/vc709/1.8`).

## Build

Needs Vivado with a licence that covers the XC7VX690T (the free edition does not; the VC709 kit shipped with a device-locked voucher, docs/RISKS.md D1).

```sh
make vc709 NCH=192          # or: vivado -mode batch -source fpga/vc709/build.tcl -tclargs 192
```

Output in `build/vc709/`: `bd_vc709.bit`, `utilization_nch192.rpt`, `timing_nch192.rpt`, `cdc_nch192.rpt`. The script stops if timing is not met (T2.1 needs WNS ≥ 0). Start with `NCH=16` to get through the first build quickly.

First-build checklist:
1. If `set_property` rejects an XDMA property name, correct it to the installed IP version (Vivado's IP customization GUI shows the names).
2. If placement reports a conflict between the XDMA transceivers and the lane pins in `vc709.xdc`, set the IP's PCIe block location to the block next to those GT quads (the pins come from the board definition and are right).
3. Read `cdc_nch*.rpt`: every crossing should be a 2-FF synchronizer, a gray pointer, or FIFO/handshake data.

## Bring-up on the host (Linux)

1. Program the FPGA (Vivado Hardware Manager), then reboot or rescan the PCIe bus so the endpoint enumerates. `lspci -d 10ee:` should list it.
2. Build and load the Xilinx XDMA driver from `github.com/Xilinx/dma_ip_drivers` (`XDMA/linux-kernel`). It creates `/dev/xdma0_user`, `/dev/xdma0_h2c_0`, `/dev/xdma0_c2h_0`. The driver is used only through these devices; nothing from it is copied into this repo (docs/LICENSES.md).
3. Build the host tools: `make build-sw`.
4. Check the registers:
   ```sh
   sw/build/bd_xdma info                 # id 0x42443031 (BD01), version 0x00020000, channels 192
   sw/build/bd_xdma regtest 1000000      # T2.2: 10^6 SCRATCH write/read pairs, 0 errors
   ```
5. Hardware bit-exactness (T2.4), the same program the simulation runs:
   ```sh
   python3 tools/hw_bitexact.py --nch 4
   python3 tools/hw_bitexact.py --nch 192 --samples 40000
   ```
   It prints `bit-exact: N records received` or the first mismatch per channel. The full T2.4 target (192 channels × 60 s) needs a faster model than the NumPy one (TEST_PLAN T2.4).

## Files

| File | Purpose |
|---|---|
| `vc709_top.sv` | Board top: XDMA, refclk buffer, MMCM, `bd_host_if`, LEDs |
| `vc709.xdc` | Pins, clocks, clock-crossing constraints |
| `build.tcl` | Project creation, XDMA generation, synthesis, implementation, reports |
| `lint_stubs.sv` | Port-only stand-ins for the Xilinx primitives and XDMA so `make lint` can check `vc709_top`'s wiring; never synthesized |
