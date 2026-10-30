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
   - GPS L1C: `tools/import_is800.py`, from the IS-GPS-800J PDF (01-AUG-2022, SHA-256 `c4aad710…5d0a`), via the same connector.
     - Cross-checks: the Legendre sequence against Table 6.2-1; all 126 codes against their printed first and last 24 chips; all 63 overlays against their final 11 bits.
     - **ICD typo:** Table 3.2-2 sheet 2 prints PRN "3" for the row between 37 and 39. This is visible on the rendered page. The row is handled as PRN 38 by an explicit, asserted rule.
   - GPS L2C: `tools/import_is200.py`, from the IS-GPS-200N PDF (01-AUG-2022, SHA-256 `54ec544b…749a`), via the same connector.
     - Cross-checks: for all 115 PRNs in Tables 3-IIa, 3-IIb and 6-II, the CM and CL generators started from the printed initial state reach the printed end state (230 checks). Only one of six candidate register conventions passes.
   - BeiDou B1I: `tools/import_bds_b1i.py`, from BDS-SIS-ICD-B1I-3.0 (China Satellite Navigation Office, 2019-02), PDF SHA-256 `7f2de6f6…2e8`.
     - **Provenance:** the official URL (`en.beidou.gov.cn/SYSTEMS/ICD/201902/P020190227702348791891.pdf`) did not answer from this environment or through the Apify connector (2026-10-27). The file was taken from the Internet Archive's unmodified (`id_`) capture of that URL of 2026-10-12. It is byte-identical to the official file: its SHA-1 equals the archive digest recorded for 13 captures from 2020 to 2026, and its length (1,209,495 bytes) equals the size in the original server's ETag. One 2024 capture is truncated at 1 MiB and was rejected by these checks.
     - **Terms:** the ICD states that CSNO prepares, distributes and interprets it; it states no licence conditions. It is treated like the GPS ICDs: code parameters are implemented from it, and the PDF is not stored or redistributed.
     - **Cross-checks** (the ICD prints no example chips): polynomials and initial phases equal the model constants (feedback stages read from Figure 4-1); all 63 codes are balanced Gold codes, as section 4.3 states, and distinct; the NH code is as printed. Wrong register conventions unbalance 30+ codes, so the balance check discriminates.
   - BeiDou B2a: `tools/import_bds_b2a.py`, from BDS-SIS-ICD-B2a-1.0 (CSNO, 2017-12), PDF SHA-256 `50e1b2b8…1880`.
     - **Provenance:** as for B1I. The official URL (`en.beidou.gov.cn/SYSTEMS/ICD/201806/P020180608518432765621.pdf`, found via the archived ICD index) did not answer, so the file came from the Internet Archive's unmodified capture of 2026-10-11. It is byte-identical to the official file: SHA-1 equals the archive digest of four captures from 2018 to 2026, and its length (1,594,977 bytes) equals the original ETag size. The 2024-11 capture differs and was not used.
     - **Cross-checks:** all four polynomials as printed; all 126 primary codes reproduce their printed first and last 24 chips (only one of eight candidate register conventions does); all 63 pilot secondary codes, built from their Weil parameters, reproduce their printed first and last 24 chips; data secondary code 00010.
     - **ICD inconsistency:** section 5.2.1 says a satellite's data and pilot generators start from the same register-2 value. Tables 5-2 and 5-3 differ for PRN 61, 62 and 63, and each of those rows reproduces its own printed chips. The tables are used as printed, and the importer asserts that exactly these three PRNs differ.
   - Galileo: `tools/import_galileo_icd.py`, from the Galileo OS SIS ICD Issue 2.2 (November 2025), PDF SHA-256 `1ca51b26…4671`, downloaded from gsc-europa.eu via the same connector. The codes come from the PDF's electronic Annex C attachments plus its tables. The importer checks that all 200 E5 codes generated from the ICD tables equal the attachments, chip for chip.

## Galileo OS SIS ICD authorisation (Annex H)

The Galileo spreading codes and other ICD "Technical Data" are EU intellectual property. They are used here under the ICD's Annex H Authorisation.

**Acceptance.** The project owner accepted the Annex H terms for this project on 2026-10-26.

**What the authorisation allows.** It is royalty-free and worldwide, covering R&D, manufacturing and sale of receivers.

**Conditions:**
- It is non-transferable and cannot be sublicensed.
- It is withdrawn if the holder challenges the validity of the EU IPRs.
- Export controls apply.
- The holder must not harm EU security interests, and must not claim EU endorsement.
- Third-party claims are defended at the holder's own cost.
- Governing law is EU/Belgian, with WIPO mediation or arbitration in Brussels.

**Obligations the project follows:**
- Code tables are stored only with the source acknowledgement and "© European Union 2025" notice that the importer writes into each generated file (Annex H.3 b).
- The ICD PDF itself is **not** committed or redistributed. Reproduction is only allowed unmodified and for non-commercial purposes (H.3 c).
- No product material may state or imply EU approval or endorsement.
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
| Galileo OS SIS ICD codes (`model/bdmodel/tables/galileo_*`) | E1/E5 primary and secondary codes | EU Annex H Authorisation (royalty-free, conditions above) | yes | Accepted 2026-10-26 |
| poppler-utils (`pdfdetach`, `pdftotext`) | Galileo importer only | GPL-2.0 | no (tool) | OK (tool use only) |
| Trimble GSOF, CMR/CMR+, RTX | — | proprietary | — | Excluded |

## Patents (separate from licences)

Independent implementation does not protect against patents. Before any commercial release, run a freedom-to-operate search on the techniques actually used. Planned watch list:
- multipath mitigation (narrow correlator variants, MEDLL-class estimators)
- RTK ambiguity resolution and validation (partial ambiguity resolution)
- semi-codeless L2 tracking (excluded anyway)
- interference mitigation (adaptive notch)
- vector tracking (if adopted)

Keep design notes dated in git: they record independent development.
