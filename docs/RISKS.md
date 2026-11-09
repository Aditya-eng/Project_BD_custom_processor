# Risk and dependency register

**Dependencies** are things outside the design team's control: access, purchases, licences. **Risks** are engineering uncertainties. Independent work continues while any dependency is open.

## Dependencies

| ID | Dependency | Blocks | Owner action | Status |
|---|---|---|---|---|
| D1 | Vivado licence that covers XC7VX690T. Virtex-7 is not in the free Standard edition (likely, AMD UG973 and vendor matrices); the VC709 kit shipped with a device-locked voucher | M2 onward | Check whether the kit voucher was redeemed; check the licence manager for XC7VX690T | open |
| D2 | NT1068 (or NT1065) evaluation board, and the datasheet under NDA if required | M3 | Contact NTLab / distributors; ask about digital output headers and IO voltage | open |
| D3 | Host PC with a PCIe x8 slot, Linux, Xilinx XDMA driver | M2 | Confirm a slot is available | open |
| D4 | Triple-frequency antenna, splitter, cables, attenuators (TEST_PLAN equipment list) | M3–M6 | Procure | open |
| D5 | Surveyed point / second antenna / nearby CORS for RTK truth | M5–M6 | Identify a site; check Survey of India CORS or IGS access | open |
| D6 | RTCM 10403.x and NMEA 0183 standards (paid) | M4 | Purchase | open |
| D7 | GitHub repository `Project-BD` | publishing this work | Create the repo; install the Claude GitHub App on it | open |

## Risks

| ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | No usable Vivado licence for the 690T | medium | blocks hardware | D1; fallback: a Kintex-7/Artix-7 board covered by the free edition, running fewer channels (the RTL is device-neutral) |
| R2 | NT1068 frequency plan (LO pairing, IF filters, ADC clock dividers) differs from ARCHITECTURE §3 assumptions | medium | rework of the frequency plan, possibly fewer simultaneous bands | Read the datasheet before buying; the RTL takes any fs and IF; the frequency plan lives in host config |
| R3 | NT1068 digital IO voltage ≠ 1.8 V VADJ on the VC709 FMC | medium | needs level translators / adapter card | Small adapter PCB; check before wiring anything |
| R4 | XDMA support for the Virtex-7 XT Gen3 integrated block in the installed Vivado version (third-party driver notes list Virtex-7 XT; not confirmed in PG195) | low | slower link or different IP | M2 uses Gen2 x8 (~4 GB/s, ~25× the need). The VC709 board definition (XilinxBoardStore 2023.2) lists `xdma` as the preferred IP for its PCIe x8 interface |
| R5 | 2-bit quantization limits interference robustness and dynamic range | known | REQ-INT tiers | Accepted for P-tier; F-tier adds a higher-resolution path (e.g. AD9361 for interference studies) |
| R6 | 192 channels fail routing/timing because of sample-bus fan-out | low | channel count | Register the sample bus per clock region; channel area estimate has ~50% headroom |
| R7 | RTK reliability needs many hours of real data | high | schedule | Automate the reset/fix scripts early (M4); run campaigns unattended |
| R8 | Patent exposure in multipath / RTK techniques | unknown | commercialization only | Freedom-to-operate search before any sale (LICENSES.md) |
| R9 | GPL code contamination | low | licence | LICENSES.md rules; review every dependency PR |
| R10 | Clean-room breach (firmware/die analysis of the E600/BD990) | low | defensibility | CLEAN_ROOM.md |
| R11 | Single developer bandwidth | high | schedule | Scope strictly to P-tier; defer every F-tier item |
| R12 | Host OS jitter delays loop updates by > 1 epoch | low | tracking robustness | Loops are validated with 1-epoch latency (REQ-TRK-004); add a 2–3 epoch test; real-time thread priority |
| R13 | IS-GPS-200N states the L2C multiplex order only indirectly ("first L2 CM-code chip starts synchronously with the end/start of week epoch"); we read it as CM first. If wrong, every L2C pseudorange is biased by one slot (~293 m) | low | L2C observables | Slot is a register bit (MODE bit 2), not hard-wired; T3.10 checks it on the first live L2C data |
| R14 | GLONASS inter-frequency biases: the 14 G1 carriers span 7.3 MHz of the analog front end, so group delay and carrier phase differ per k. That biases code observables and blocks integer ambiguity resolution between GLONASS satellites unless calibrated | medium | GLONASS RTK | Calibrate per-k code and phase biases on zero baseline (T3.8, T4.2); report them in RTCM; start RTK with GPS/Galileo/BeiDou only if calibration is late |
| R15 | The VC709 build was written without Vivado: XDMA property and port names, and the PCIe hard-block placement relative to the board's lane pins, are unverified | high (some edit needed) | days on the first build | Pins come from the Xilinx board definition, so a placement mismatch fails loudly; `vc709_top` wiring is lint-checked against stubs; `build.tcl` stops at the first wrong property name |
| R16 | Playback FIFO maps to ~2.8k LUTs of distributed RAM (Yosys) | low | area | Replace with a block-RAM FIFO (registered read) if area gets tight |
