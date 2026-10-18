# Project BD

An independent multi-band, multi-constellation GNSS receiver, aiming for capability in the class of a high-end survey OEM board (Trimble BD990 used as the performance reference only).

Phase 1 runs on a **Xilinx VC709 (Virtex-7 XC7VX690T)**: 192 correlator channels in the FPGA, with tracking loops, acquisition, navigation and RTK on a host PC over PCIe.

> Status (2026-10-18): requirements frozen (v1); architecture chosen. GPS L1 C/A reference receiver works in simulation. First RTL slice (C/A code generator + tracking channel) is verified bit-exact against the model. **No hardware has been built or measured yet.**

## Layout

| Path | Contents |
|---|---|
| `docs/REQUIREMENTS.md` | Frozen requirements v1 (prototype tier P, final-product tier F) |
| `docs/ARCHITECTURE.md` | Platform, RF front end, frequency plan, channel contract, budgets |
| `docs/TEST_PLAN.md` | T0–T4 tests including RF bench tests and the equipment list |
| `docs/SCHEDULE.md` | Milestones and time estimate |
| `docs/RISKS.md` | Dependencies and engineering risks |
| `docs/LICENSES.md`, `docs/CLEAN_ROOM.md` | Licence policy, third-party register, clean-room rules |
| `model/bdmodel/` | Python reference: C/A codes, bit-exact correlator, signal simulator, acquisition, tracking |
| `rtl/` | SystemVerilog: `track_channel.sv`, `gps_ca_gen.sv`, generated carrier LUT |
| `tb/` | cocotb testbenches comparing RTL to the model |
| `tools/` | Generators (carrier LUT) |

## Running the tests

```sh
sudo apt-get install iverilog verilator     # Icarus >= 12, Verilator >= 5
pip install -r requirements-dev.txt
make test        # LUT check, lint, model tests, RTL-vs-model tests
make estimate    # optional: Yosys 7-series resource estimate (needs yosys)
```

## Licence

All rights reserved by the project owner until a licence is chosen (see `docs/LICENSES.md`).
