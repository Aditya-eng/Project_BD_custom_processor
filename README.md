# Project BD

An independent multi-band, multi-constellation GNSS receiver, aiming for capability in the class of a high-end survey OEM board (Trimble BD990 used as the performance reference only).

Phase 1 runs on a **Xilinx VC709 (Virtex-7 XC7VX690T)**: 192 correlator channels in the FPGA, with tracking loops, acquisition, navigation and RTK on a host PC over PCIe.

> Status (M1, 2026-10-18):
> - Requirements frozen (v1); architecture chosen.
> - In simulation, the GPS L1 C/A reference receiver goes from IF samples to a position fix (3.7 m, 5 ns on a synthetic sky).
> - The multi-channel FPGA core (`bd_core`: channels, timebase/PPS, collector, register bus) is verified bit-exact against the model.
> - The C++ host tracking loop is bit-identical to the Python one.
> - **No hardware has been built or measured yet.**

## Layout

| Path | Contents |
|---|---|
| `docs/REQUIREMENTS.md` | Frozen requirements v1 (prototype tier P, final-product tier F) |
| `docs/ARCHITECTURE.md` | Platform, RF front end, frequency plan, channel contract, budgets |
| `docs/REGISTERS.md` | bd_core register map, timing semantics, record format |
| `docs/TEST_PLAN.md` | T0–T4 tests including RF bench tests and the equipment list |
| `docs/SCHEDULE.md` | Milestones and time estimate |
| `docs/RISKS.md` | Dependencies and engineering risks |
| `docs/LICENSES.md`, `docs/CLEAN_ROOM.md` | Licence policy, third-party register, clean-room rules |
| `model/bdmodel/` | Python reference: C/A and L5 codes, signal specs, bit-exact correlator (incl. BOC(1,1)), simulators, acquisition, tracking, LNAV, ephemeris, geometry scenario, PVT |
| `rtl/` | SystemVerilog: `bd_core` (top), `channel_bank` (channels + collector), `timebase`, `sample_mux`, `track_channel`, `gps_ca_gen` |
| `sw/` | C++17 host library: record parser, tracking loop; `bd_loopcheck` replay tool |
| `tb/` | cocotb testbenches comparing RTL to the model (`test_rtl.py` per block, `test_core.py` integration) |
| `tools/` | Generators (carrier LUT) and ICD table importers |

## Running the tests

```sh
sudo apt-get install iverilog verilator cmake g++   # Icarus >= 12, Verilator >= 5
pip install -r requirements-dev.txt
make test        # LUT check, lint, model, RTL-vs-model, C++ build + C++-vs-Python
make estimate    # optional: Yosys 7-series resource estimate (needs yosys)
```

## Licence

All rights reserved by the project owner until a licence is chosen (see `docs/LICENSES.md`).
