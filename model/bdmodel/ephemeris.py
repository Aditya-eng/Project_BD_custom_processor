"""GPS broadcast ephemeris: satellite position and clock (IS-GPS-200 20.3.3.4.3, Table 20-IV)."""
from dataclasses import dataclass

import numpy as np

C = 299792458.0
MU = 3.986005e14                # WGS-84 value used by GPS, m^3/s^2
OMEGA_E = 7.2921151467e-5       # rad/s
F_REL = -4.442807633e-10        # s/m^0.5
GPS_PI = 3.1415926535898        # value specified by IS-GPS-200
HALF_WEEK = 302400.0


@dataclass
class Ephemeris:
    prn: int
    week: int
    toc: float
    af0: float
    af1: float
    af2: float
    tgd: float
    iodc: int
    iode: int
    toe: float
    sqrt_a: float
    e: float
    m0: float        # rad
    delta_n: float   # rad/s
    omega0: float    # rad
    i0: float        # rad
    omega: float     # rad (argument of perigee)
    omega_dot: float # rad/s
    idot: float      # rad/s
    cuc: float = 0.0
    cus: float = 0.0
    crc: float = 0.0
    crs: float = 0.0
    cic: float = 0.0
    cis: float = 0.0
    health: int = 0
    ura: int = 0


def _wrap_week(dt):
    dt = np.asarray(dt, dtype=np.float64)
    return dt - np.round(dt / (2 * HALF_WEEK)) * 2 * HALF_WEEK


def _ecc_anomaly(eph: Ephemeris, t):
    a = eph.sqrt_a ** 2
    n = np.sqrt(MU / a ** 3) + eph.delta_n
    tk = _wrap_week(np.asarray(t, dtype=np.float64) - eph.toe)
    m = eph.m0 + n * tk
    e_anom = m.copy() if np.ndim(m) else float(m)
    for _ in range(12):
        e_anom = m + eph.e * np.sin(e_anom)
    return e_anom, tk, a


def sat_clock(eph: Ephemeris, t_sv):
    """SV clock offset dt (s) for L1 C/A at SV time t_sv (relativity and TGD included).

    GPS time t = t_sv - dt.
    """
    t = np.asarray(t_sv, dtype=np.float64)
    for _ in range(2):
        dtc = _wrap_week(t - eph.toc)
        e_anom, _, _ = _ecc_anomaly(eph, t)
        dt = (eph.af0 + eph.af1 * dtc + eph.af2 * dtc ** 2
              + F_REL * eph.e * eph.sqrt_a * np.sin(e_anom) - eph.tgd)
        t = np.asarray(t_sv) - dt
    return dt


def sat_position(eph: Ephemeris, t):
    """ECEF position (m) at GPS time t (array or scalar); returns shape (..., 3)."""
    e_anom, tk, a = _ecc_anomaly(eph, t)
    v = np.arctan2(np.sqrt(1 - eph.e ** 2) * np.sin(e_anom), np.cos(e_anom) - eph.e)
    phi = v + eph.omega
    s2, c2 = np.sin(2 * phi), np.cos(2 * phi)
    u = phi + eph.cus * s2 + eph.cuc * c2
    r = a * (1 - eph.e * np.cos(e_anom)) + eph.crs * s2 + eph.crc * c2
    i = eph.i0 + eph.cis * s2 + eph.cic * c2 + eph.idot * tk
    xp, yp = r * np.cos(u), r * np.sin(u)
    om = eph.omega0 + (eph.omega_dot - OMEGA_E) * tk - OMEGA_E * eph.toe
    x = xp * np.cos(om) - yp * np.cos(i) * np.sin(om)
    y = xp * np.sin(om) + yp * np.cos(i) * np.cos(om)
    z = yp * np.sin(i)
    return np.stack([x, y, z], axis=-1)


def rotate_earth(pos, tau):
    """Rotate ECEF positions by the Earth's rotation during signal travel time tau."""
    pos = np.asarray(pos, dtype=np.float64)
    ang = OMEGA_E * np.asarray(tau, dtype=np.float64)
    c, s = np.cos(ang), np.sin(ang)
    x = c * pos[..., 0] + s * pos[..., 1]
    y = -s * pos[..., 0] + c * pos[..., 1]
    return np.stack([x, y, pos[..., 2]], axis=-1)


# ---- WGS-84 helpers ----
WGS84_A = 6378137.0
WGS84_F = 1 / 298.257223563
WGS84_E2 = WGS84_F * (2 - WGS84_F)


def lla_to_ecef(lat_deg, lon_deg, h):
    lat, lon = np.radians(lat_deg), np.radians(lon_deg)
    n = WGS84_A / np.sqrt(1 - WGS84_E2 * np.sin(lat) ** 2)
    return np.array([(n + h) * np.cos(lat) * np.cos(lon),
                     (n + h) * np.cos(lat) * np.sin(lon),
                     (n * (1 - WGS84_E2) + h) * np.sin(lat)])


def ecef_to_lla(p):
    x, y, z = p
    lon = np.arctan2(y, x)
    r = np.hypot(x, y)
    lat = np.arctan2(z, r * (1 - WGS84_E2))
    for _ in range(8):
        n = WGS84_A / np.sqrt(1 - WGS84_E2 * np.sin(lat) ** 2)
        h = r / np.cos(lat) - n
        lat = np.arctan2(z, r * (1 - WGS84_E2 * n / (n + h)))
    return np.degrees(lat), np.degrees(lon), h


def elevation_azimuth(rx, sat):
    lat, lon, _ = ecef_to_lla(rx)
    la, lo = np.radians(lat), np.radians(lon)
    d = np.asarray(sat) - rx
    east = -np.sin(lo) * d[..., 0] + np.cos(lo) * d[..., 1]
    north = (-np.sin(la) * np.cos(lo) * d[..., 0] - np.sin(la) * np.sin(lo) * d[..., 1]
             + np.cos(la) * d[..., 2])
    up = (np.cos(la) * np.cos(lo) * d[..., 0] + np.cos(la) * np.sin(lo) * d[..., 1]
          + np.sin(la) * d[..., 2])
    return np.degrees(np.arctan2(up, np.hypot(east, north))), np.degrees(np.arctan2(east, north))
