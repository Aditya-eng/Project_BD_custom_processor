"""QZSS (Michibiki) signals that share the GPS signal designs, using the GPS ICDs'
additional code tables:

  L1 C/A  IS-GPS-200N Table 6-I    (tools/import_is200_ca.py)
  L1C     IS-GPS-800J Tables 6.3-1, 6.3-2 (tools/import_is800.py)
  L2C     IS-GPS-200N Table 6-II   (tools/import_is200.py)
  L5      IS-GPS-705J Table 6-II   (tools/import_is705.py)

QZSS uses PRN 193-202 for these signals. That assignment is from the QZSS interface
specification (IS-QZSS-PNT), which has not been fetched for this project (its download
page asks the reader to accept a disclaimer first). The GPS ICDs give the codes for every
PRN 64-210, but not which system uses which. Data rates, secondary codes and modulation
are the GPS ones. QZSS-only signals (L1S/SLAS, L6/CLAS, L5S) are not covered.
"""
QZSS_PRNS = range(193, 203)
