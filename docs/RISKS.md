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
| R4 | XDMA support for the Virtex-7 XT Gen3 integrated block in the installed Vivado version (third-party driver notes list Virtex-7 XT; not confirmed in PG195) | low–medium | slower link or different IP | Fallback: Gen2 x8 is still > 3 GB/s, ~40× the needed bandwidth |
| R5 | 2-bit quantization limits interference robustness and dynamic range | known | REQ-INT tiers | Accepted for P-tier; F-tier adds a higher-resolution path (e.g. AD9361 for interference studies) |
| R6 | 192 channels fail routing/timing because of sample-bus fan-out | low | channel count | Register the sample bus per clock region; channel area estimate has ~50% headroom |
| R7 | RTK reliability needs many hours of real data | high | schedule | Automate the reset/fix scripts early (M4); run campaigns unattended |
| R8 | Patent exposure in multipath / RTK techniques | unknown | commercialization only | Freedom-to-operate search before any sale (LICENSES.md) |
| R9 | GPL code contamination | low | licence | LICENSES.md rules; review every dependency PR |
| R10 | Clean-room breach (firmware/die analysis of the E600/BD990) | low | defensibility | CLEAN_ROOM.md |
| R11 | Single developer bandwidth | high | schedule | Scope strictly to P-tier; defer every F-tier item |
| R12 | Host OS jitter delays loop updates by > 1 epoch | low | tracking robustness | Loops are validated with 1-epoch latency (REQ-TRK-004); add a 2–3 epoch test; real-time thread priority |
