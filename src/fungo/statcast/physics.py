"""Nathan (2021) pitch-physics derived columns — stdlib ``math`` only.

Operates on ``list[dict]`` rows (Savant CSV output). Each required input column
must be castable to float; rows missing any input (or producing an invalid
physical solution) are returned unchanged, with no derived keys.

Required input columns per row:
    ``release_extension``, ``vx0``, ``vy0``, ``vz0``, ``ax``, ``ay``, ``az``,
    ``spinx``, ``spiny``, ``spinz``

Gotcha: Savant's pitch-level CSV export has ``vx0/vy0/vz0`` and ``ax/ay/az`` but
NOT ``spinx/spiny/spinz`` — those come from aggregate Savant exports or from
TrackMan. For standard search rows, use ``spin_axis`` + ``release_spin_rate``
for partial analysis, or bring your own spin-component columns.

Output columns (all floats), per :data:`DERIVED_COLUMNS`: induced vs gyro
spin, Magnus / non-Magnus decomposition, spin efficiency, drag, lift, tilt,
release mechanics, and flight timing.

Reference source: Nathan (2021), driveline/solving-physics/ref/nathan.py.
"""

from __future__ import annotations

import math
from typing import Any

#####################################################################
# Constants
#####################################################################

# Environmental constant
K = 0.005383
# Standard gravity (ft/s^2)
G = 32.174
# Distance of the pitcher's mound (ft)
MOUND_DISTANCE = 60.5
# Distance of Statcast initial measurement (ft from home plate)
STATCAST_INITIAL_MEASUREMENT = 50.0
INCHES_PER_FOOT = 12.0
# Length of home plate (ft)
PLATE_LENGTH = 17.0 / INCHES_PER_FOOT
# Ball circumference (in)
BALL_CIRCUMFERENCE = 9.125
# Nathan (2021) Hill function coefficients
NATHAN_HILL_A = 0.4152
NATHAN_HILL_B = 0.1904
NATHAN_HILL_N = 1.401

REQUIRED_INPUTS: tuple[str, ...] = (
    "release_extension",
    "vx0",
    "vy0",
    "vz0",
    "ax",
    "ay",
    "az",
    "spinx",
    "spiny",
    "spinz",
)

DERIVED_COLUMNS: tuple[str, ...] = (
    "spin_rate",
    "release_pos_y",
    "tR",
    "vxR",
    "vyR",
    "vzR",
    "tF",
    "vxbar",
    "vybar",
    "vzbar",
    "vbar",
    "vx_hat",
    "vy_hat",
    "vz_hat",
    "aD",
    "aTx",
    "aTy",
    "aTz",
    "aT",
    "aTx_hat",
    "aTy_hat",
    "aTz_hat",
    "phiT",
    "MTx",
    "MTz",
    "MT",
    "wx_hat",
    "wy_hat",
    "wz_hat",
    "spin_eff",
    "aLx_hat",
    "aLy_hat",
    "aLz_hat",
    "phiL",
    "axis_shift",
    "L_align",
    "ML",
    "MS",
    "MLx",
    "MLz",
    "MSx",
    "MSz",
    "phiS",
    "S",
    "aMx_hat",
    "aMy_hat",
    "aMz_hat",
    "phiM",
    "eff_S",
    "CL",
    "aM",
    "M_prop",
    "MM",
    "MMx",
    "MMz",
    "MNx",
    "MNz",
    "MN",
    "phiN",
)


#####################################################################
# Helpers
#####################################################################


def _to_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _time_in_air(
    velocity: float,
    acceleration: float,
    position: float,
    adjustment: float,
    positive: bool,
) -> float | None:
    """Solve the quadratic for time in air; ``None`` if discriminant is negative."""
    direction_factor = 1 if positive else -1
    disc = velocity**2 - 2 * acceleration * direction_factor * (position - adjustment)
    if disc < 0:
        return None
    return (-velocity - math.sqrt(disc)) / acceleration


#####################################################################
# Per-row computation
#####################################################################


def compute_row(row: dict[str, Any]) -> dict[str, Any] | None:
    """Compute Nathan derived quantities for a single row dict.

    Args:
        row: A pitch row dict. Must contain every name in
            :data:`REQUIRED_INPUTS`, each castable to ``float``.

    Returns:
        A dict of derived floats (keys = :data:`DERIVED_COLUMNS`), or ``None`` if
        required inputs are missing or produce an invalid physical solution.
    """
    inputs: dict[str, float] = {}
    for name in REQUIRED_INPUTS:
        value = _to_float(row.get(name))
        if value is None:
            return None
        inputs[name] = value

    release_extension = inputs["release_extension"]
    vx0, vy0, vz0 = inputs["vx0"], inputs["vy0"], inputs["vz0"]
    ax, ay, az = inputs["ax"], inputs["ay"], inputs["az"]
    spinx, spiny, spinz = inputs["spinx"], inputs["spiny"], inputs["spinz"]

    spin_rate = math.sqrt(spinx**2 + spiny**2 + spinz**2)
    if spin_rate == 0:
        return None

    release_pos_y = MOUND_DISTANCE - release_extension

    tR = _time_in_air(
        vy0, ay, release_pos_y, STATCAST_INITIAL_MEASUREMENT, positive=False
    )
    if tR is None:
        return None

    vxR = vx0 + ax * tR
    vyR = vy0 + ay * tR
    vzR = vz0 + az * tR

    tF = _time_in_air(vyR, ay, release_pos_y, PLATE_LENGTH, positive=True)
    if tF is None:
        return None

    vxbar = (2 * vxR + ax * tF) / 2
    vybar = (2 * vyR + ay * tF) / 2
    vzbar = (2 * vzR + az * tF) / 2
    vbar = math.sqrt(vxbar**2 + vybar**2 + vzbar**2)
    if vbar == 0:
        return None

    vx_hat = vxbar / vbar
    vy_hat = vybar / vbar
    vz_hat = vzbar / vbar

    aD = -((ax * vx_hat) + (ay * vy_hat) + ((az + G) * vz_hat))

    aTx = ax + aD * vx_hat
    aTy = ay + aD * vy_hat
    aTz = az + aD * vz_hat + G
    aT = math.sqrt(aTx**2 + aTy**2 + aTz**2)
    if aT == 0:
        return None

    aTx_hat = aTx / aT
    aTy_hat = aTy / aT
    aTz_hat = aTz / aT
    phiT = math.degrees(math.atan2(aTz_hat, aTx_hat))

    MTx = 0.5 * aTx * (tF**2) * INCHES_PER_FOOT
    MTz = 0.5 * aTz * (tF**2) * INCHES_PER_FOOT
    MT = math.sqrt(MTx**2 + MTz**2)

    wx_hat = spinx / spin_rate
    wy_hat = spiny / spin_rate
    wz_hat = spinz / spin_rate

    cx = wy_hat * vz_hat - wz_hat * vy_hat
    cy = wz_hat * vx_hat - wx_hat * vz_hat
    cz = wx_hat * vy_hat - wy_hat * vx_hat
    spin_eff = math.sqrt(cx**2 + cy**2 + cz**2)
    if spin_eff == 0:
        return None

    aLx_hat = cx / spin_eff
    aLy_hat = cy / spin_eff
    aLz_hat = cz / spin_eff
    phiL = math.degrees(math.atan2(aLz_hat, aLx_hat))
    axis_shift = phiT - phiL
    L_align = aTx_hat * aLx_hat + aTy_hat * aLy_hat + aTz_hat * aLz_hat
    ML = MT * L_align
    ms_sq = MT**2 - ML**2
    MS = math.sqrt(ms_sq) if ms_sq >= 0 else 0.0
    MLx = aLx_hat * ML
    MLz = aLz_hat * ML
    MSx = MTx - MLx
    MSz = MTz - MLz
    phiS = math.degrees(math.atan2(MSz, MSx))

    aMx_hat = aLx_hat
    aMy_hat = aLy_hat
    aMz_hat = aLz_hat
    phiM = math.degrees(math.atan2(aMz_hat, aMx_hat))

    S = spin_rate * BALL_CIRCUMFERENCE / (720 * vbar)
    eff_S = S * spin_eff
    CL = (
        (NATHAN_HILL_A * S**NATHAN_HILL_N)
        / (NATHAN_HILL_B**NATHAN_HILL_N + S**NATHAN_HILL_N)
        * spin_eff
    )
    aM = K * CL * vbar**2
    M_prop = aM / aT
    MM = MT * M_prop
    MMx = MM * math.cos(math.radians(phiM))
    MMz = MM * math.sin(math.radians(phiM))
    MNx = MTx - MMx
    MNz = MTz - MMz
    MN = math.sqrt(MNx**2 + MNz**2)
    phiN = math.degrees(math.atan2(MNz, MNx))

    return {
        "spin_rate": spin_rate,
        "release_pos_y": release_pos_y,
        "tR": tR,
        "vxR": vxR,
        "vyR": vyR,
        "vzR": vzR,
        "tF": tF,
        "vxbar": vxbar,
        "vybar": vybar,
        "vzbar": vzbar,
        "vbar": vbar,
        "vx_hat": vx_hat,
        "vy_hat": vy_hat,
        "vz_hat": vz_hat,
        "aD": aD,
        "aTx": aTx,
        "aTy": aTy,
        "aTz": aTz,
        "aT": aT,
        "aTx_hat": aTx_hat,
        "aTy_hat": aTy_hat,
        "aTz_hat": aTz_hat,
        "phiT": phiT,
        "MTx": MTx,
        "MTz": MTz,
        "MT": MT,
        "wx_hat": wx_hat,
        "wy_hat": wy_hat,
        "wz_hat": wz_hat,
        "spin_eff": spin_eff,
        "aLx_hat": aLx_hat,
        "aLy_hat": aLy_hat,
        "aLz_hat": aLz_hat,
        "phiL": phiL,
        "axis_shift": axis_shift,
        "L_align": L_align,
        "ML": ML,
        "MS": MS,
        "MLx": MLx,
        "MLz": MLz,
        "MSx": MSx,
        "MSz": MSz,
        "phiS": phiS,
        "S": S,
        "aMx_hat": aMx_hat,
        "aMy_hat": aMy_hat,
        "aMz_hat": aMz_hat,
        "phiM": phiM,
        "eff_S": eff_S,
        "CL": CL,
        "aM": aM,
        "M_prop": M_prop,
        "MM": MM,
        "MMx": MMx,
        "MMz": MMz,
        "MNx": MNx,
        "MNz": MNz,
        "MN": MN,
        "phiN": phiN,
    }


#####################################################################
# Public API
#####################################################################


def add_spin_columns(
    rows: list[dict[str, Any]], *, inplace: bool = False
) -> list[dict[str, Any]]:
    """Add Nathan (2021) derived physics columns to each row.

    Args:
        rows: ``list[dict]`` — typically Savant search output.
        inplace: If True, mutate the input dicts. Otherwise return new dicts.

    Returns:
        ``list[dict]`` with the :data:`DERIVED_COLUMNS` set. Rows missing
        required inputs (or yielding an invalid solution) are left untouched.
    """
    out: list[dict[str, Any]] = []
    for row in rows:
        target = row if inplace else dict(row)
        derived = compute_row(row)
        if derived is not None:
            target.update(derived)
        out.append(target)
    return out


def axis_to_clock(axis_deg: float | str | None) -> str | None:
    """Convert a Savant ``spin_axis`` (degrees) to a clock-face tilt string.

    The Savant convention: ``0`` = 12:00, ``90`` = 3:00, ``180`` = 6:00,
    ``270`` = 9:00.

    Args:
        axis_deg: Spin axis in degrees (numeric or numeric string), or ``None``.

    Returns:
        A clock-face string like ``"1:30"``, or ``None`` if ``axis_deg`` is
        ``None``.
    """
    if axis_deg is None:
        return None
    axis_deg = float(axis_deg) % 360.0
    total_minutes = (axis_deg / 360.0) * 12 * 60
    hour = int(total_minutes // 60) % 12
    if hour == 0:
        hour = 12
    minute = round(total_minutes - (total_minutes // 60) * 60)
    if minute == 60:
        minute = 0
        hour = (hour % 12) + 1
    return f"{hour}:{minute:02d}"
