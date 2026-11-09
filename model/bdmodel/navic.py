"""NavIC (IRNSS) L5 SPS: BPSK(1) on 1176.45 MHz, 1023-chip Gold codes at 1.023 Mcps
(1 ms), navigation data at 50 symbols per second (rate 1/2 FEC), i.e. one symbol per
20 code epochs, no secondary code. Source: ISRO-IRNSS-ICD-SPS-1.1 (August 2017), 4.1.

The code generator is the IS-GPS-200 C/A register pair (the ICD gives the same G1 and G2
polynomials, G1 started at all ones); only the G2 initial state differs per PRN.

The per-PRN initial states are NOT in this repository. The ICD's cover page says its
contents shall not be copied, in whole or in part, or divulged without ISRO's written
consent. tools/import_navic.py reads your own copy of the PDF and writes
model/bdmodel/tables/navic_l5_table.py locally (listed in .gitignore). See
docs/LICENSES.md.
"""
from .gps_ca import CA_CHIP_RATE, CA_LEN, ca_code_from_g2_init

NAVIC_L5_FREQ = 1176.45e6
NAVIC_CHIP_RATE = CA_CHIP_RATE
NAVIC_LEN = CA_LEN
SYMBOL_RATE_SPS = 50
EPOCHS_PER_SYMBOL = 20

_MISSING = ("NavIC code table not generated: run "
            "tools/import_navic.py <your copy of ISRO-IRNSS-ICD-SPS-1.1.pdf> "
            "(the table is not distributed with this repository; see docs/LICENSES.md)")


def table_available() -> bool:
    try:
        from .tables import navic_l5_table  # noqa: F401
    except ImportError:
        return False
    return True


def l5_code(prn: int):
    """1023-chip L5 SPS code as uint8 logic values (0/1)."""
    try:
        from .tables.navic_l5_table import NAVIC_L5_G2_INIT
    except ImportError as e:
        raise RuntimeError(_MISSING) from e
    return ca_code_from_g2_init([int(b) for b in NAVIC_L5_G2_INIT[prn]])
