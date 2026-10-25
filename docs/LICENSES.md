# Licence policy and third-party register

## Project licence

No licence is granted yet: **all rights reserved by the project owner**. The owner must choose before any outside contributor joins or any binary is distributed. Options:
- Keep it proprietary (default).
- Apache-2.0 for software plus CERN-OHL-P/-W for hardware, if the project should be open.

## Rules

1. **Shipped code** (FPGA bitstream sources, host daemon, firmware) may only include permissive-licence code: MIT, BSD-2/3, Apache-2.0, ISC, zlib.
2. **GPL/LGPL/AGPL code is never copied, linked or ported** into shipped code. It may be used as an external tool (a simulator, or GNSS-SDR run on a recorded file to compare results), so long as no source text moves into this repo.
3. Every third-party component gets a row below **before** it is added. The row records the licence as read from the component's own `LICENSE` file at the pinned version.
4. Vendor IP (Xilinx XDMA, MIG, FIFO generator, clocking wizard) may be used on the FPGA prototype. It must be replaced before any non-Xilinx target (ASIC), because Xilinx IP licences restrict use to Xilinx devices.
5. Interface specifications (IS-GPS-200/705/800, Galileo OS SIS ICD, BDS ICDs, IRNSS SPS ICD, QZSS IS-QZSS, RTCM 10403.x, NMEA 0183, RINEX) are implemented from the documents themselves.
   - ICD tables enter the repo only through an importer in `tools/` that parses a text extraction of the official document and cross-checks every row before writing. The ICD PDFs are not stored in the repo.
   - GPS L5: `tools/import_is705.py`, from IS-GPS-705J (01-AUG-2022), downloaded from gps.gov via the project owner's Apify web-fetch connector (this environment's network policy blocks gps.gov).
   - RTCM 10403.x and NMEA 0183 are paid standards: buy a copy; do not copy text from them into the repo.

## Third-party register

| Component | Use | Licence | Shipped? | Status |
|---|---|---|---|---|
| NumPy, SciPy | reference model, tools | BSD-3-Clause | no (dev) | OK |
| cocotb | RTL testbenches | BSD-3-Clause | no (dev) | OK |
| pytest | tests | MIT | no (dev) | OK |
| Icarus Verilog | simulator | GPL-2.0 | no (tool) | OK (tool use only) |
| Verilator | lint/simulator | LGPL-3.0 / Artistic-2.0 | no (tool) | OK (tool use only) |
| Yosys | early synthesis estimates | ISC | no (tool) | OK |
| Vivado + XDMA/MIG/FIFO IP | FPGA implementation | Xilinx EULA / IP licence | bitstream only | OK for the prototype; replace for an ASIC |
| RTKLIB 2.4.3 | v1 RTK/PPP engine (host) | BSD-2-Clause **plus two additional clauses** (from 2.4.2; earlier versions were GPLv3) | yes | **Pending:** read the extra clauses at the pinned commit before linking; demo5 fork licence also unverified |
| GNSS-SDR | external cross-check on recorded files only | GPL-3.0-or-later | **never** | Tool use only; no code or ports into this repo |
| Trimble GSOF, CMR/CMR+, RTX | — | proprietary | — | Excluded |

## Patents (separate from licences)

Independent implementation does not protect against patents. Before any commercial release, run a freedom-to-operate search on the techniques actually used. Planned watch list:
- multipath mitigation (narrow correlator variants, MEDLL-class estimators)
- RTK ambiguity resolution and validation (partial ambiguity resolution)
- semi-codeless L2 tracking (excluded anyway)
- interference mitigation (adaptive notch)
- vector tracking (if adopted)

Keep design notes dated in git: they record independent development.
