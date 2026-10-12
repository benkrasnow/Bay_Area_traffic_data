"""Generate SYNTHETIC demo data in the same format as the real PeMS pipeline.

Freeway geometry is hand-approximated (a few hundred metres off the real roads) and traffic
is simulated, so the app is fully explorable before you have a PeMS account. Replace with
real data using tools/pems_to_app.py.

    python tools/make_demo_data.py            # writes ./data
"""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from writer import write_dataset  # noqa: E402

START_YEAR, END_YEAR, SLOT_MIN = 2015, 2025, 60
SPD = 1440 // SLOT_MIN
rng = np.random.default_rng(42)

# name: (dir_pair, waypoints lat/lon in increasing-PM direction, am/pm intensity of dir[0], dir[1])
# increasing PM = North or East. dir pair = (increasing, decreasing).
FWYS = {
    "101": (("N", "S"), [(37.13, -121.64), (37.25, -121.78), (37.33, -121.89), (37.37, -121.93), (37.41, -122.06),
                         (37.45, -122.14), (37.50, -122.21), (37.57, -122.29), (37.62, -122.38), (37.66, -122.40),
                         (37.74, -122.40), (37.77, -122.405), (37.79, -122.425), (37.80, -122.44), (37.82, -122.478),
                         (37.86, -122.49), (37.88, -122.51), (37.93, -122.53), (37.97, -122.52), (38.05, -122.54),
                         (38.10, -122.57), (38.24, -122.64), (38.44, -122.71)],
            (0.55, 0.95), (0.95, 0.55)),
    "280": (("N", "S"), [(37.33, -121.87), (37.32, -121.97), (37.32, -122.06), (37.36, -122.15), (37.40, -122.23),
                         (37.47, -122.31), (37.55, -122.36), (37.62, -122.44), (37.70, -122.465), (37.73, -122.43),
                         (37.75, -122.395), (37.775, -122.395)],
            (0.45, 0.8), (0.8, 0.45)),
    "880": (("N", "S"), [(37.33, -121.89), (37.37, -121.91), (37.45, -121.94), (37.53, -121.97), (37.60, -122.05),
                         (37.68, -122.12), (37.74, -122.18), (37.80, -122.27), (37.83, -122.30)],
            (0.6, 0.95), (0.95, 0.6)),
    "80": (("E", "W"), [(37.79, -122.39), (37.81, -122.34), (37.83, -122.30), (37.87, -122.31), (37.92, -122.34),
                        (37.99, -122.33), (38.04, -122.25), (38.10, -122.23), (38.25, -122.10), (38.35, -121.97)],
           (0.5, 1.0), (1.0, 0.5)),
    "580": (("E", "W"), [(37.81, -122.28), (37.78, -122.20), (37.75, -122.17), (37.73, -122.07), (37.70, -121.93),
                         (37.70, -121.80), (37.72, -121.60), (37.72, -121.45)],
            (0.9, 0.6), (0.6, 0.9)),
    "680": (("N", "S"), [(37.40, -121.87), (37.45, -121.90), (37.52, -121.93), (37.60, -121.92), (37.70, -121.92),
                         (37.80, -122.00), (37.90, -122.06), (37.99, -122.09), (38.05, -122.12)],
            (0.55, 0.95), (0.95, 0.55)),
    "237": (("E", "W"), [(37.40, -122.06), (37.405, -122.00), (37.41, -121.96), (37.41, -121.92)],
            (0.9, 0.7), (0.7, 0.9)),
    "85": (("N", "S"), [(37.23, -121.96), (37.31, -122.03), (37.37, -122.07), (37.40, -122.08)],
           (0.6, 0.85), (0.85, 0.6)),
    "92": (("E", "W"), [(37.53, -122.33), (37.57, -122.30), (37.59, -122.20), (37.62, -122.10)],
           (0.8, 0.6), (0.6, 0.8)),
    "24": (("E", "W"), [(37.83, -122.28), (37.88, -122.18), (37.89, -122.12), (37.90, -122.06)],
           (0.5, 0.9), (0.9, 0.5)),
    "4": (("E", "W"), [(38.01, -122.25), (38.01, -122.12), (38.00, -122.00), (38.00, -121.80)],
          (0.8, 0.6), (0.6, 0.8)),
}


def miles(a, b):
    dy = (b[0] - a[0]) * 69.0
    dx = (b[1] - a[1]) * 69.0 * math.cos(math.radians(a[0]))
    return math.hypot(dx, dy)


def stations_along(fwy, dirs, pts, intens):
    """Place a detector every ~0.5 mi along the polyline, for both directions."""
    seg = [miles(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    total = sum(seg)
    out = []
    for d, di in zip(dirs, (0, 1)):
        off = 0.0004 if di == 0 else -0.0004      # offset the two directions so both show on the map
        n = int(total / 0.5)
        for k in range(n + 1):
            dist = total * k / n
            acc, i = 0.0, 0
            while i < len(seg) - 1 and acc + seg[i] < dist:
                acc += seg[i]
                i += 1
            t = (dist - acc) / seg[i] if seg[i] else 0
            lat = pts[i][0] + (pts[i + 1][0] - pts[i][0]) * t
            lon = pts[i][1] + (pts[i + 1][1] - pts[i][1]) * t
            # perpendicular offset
            dlat, dlon = pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]
            norm = math.hypot(dlat, dlon) or 1
            lat += -dlon / norm * off
            lon += dlat / norm * off
            out.append({"id": 400000 + len(out) + hash(fwy + d) % 1000 * 1000 + k, "fwy": int(fwy), "dir": d,
                        "lat": lat, "lon": lon, "pm": dist, "lanes": 4 if di == 0 else 4,
                        "frac": k / n, "am": intens[di][0], "pm_int": intens[di][1]})
    return out


def peak(h, c, s):
    return np.exp(-0.5 * ((h - c) / s) ** 2)


def year_month_factor(months):
    """Overall demand multiplier per month index (trend, COVID collapse, partial recovery)."""
    anchors = {2015: .82, 2016: .88, 2017: .94, 2018: 1.0, 2019: 1.03, 2020: 1.0, 2021: .62, 2022: .78,
               2023: .86, 2024: .91, 2025: .94}
    f = np.zeros(months)
    for m in range(months):
        y = START_YEAR + m // 12
        f[m] = anchors[y] + (anchors.get(y + 1, anchors[y]) - anchors[y]) * ((m % 12) / 12) * 0.5
        if y == 2020:                          # lockdown: Mar-Apr collapse, slow summer return
            mo = m % 12
            f[m] = [1.03, 1.03, .45, .30, .40, .48, .52, .54, .55, .57, .58, .55][mo]
    return f


def main(out_dir):
    months = (END_YEAR - START_YEAR + 1) * 12
    hours = np.arange(SPD) * SLOT_MIN / 60.0 + SLOT_MIN / 120.0
    yf = year_month_factor(months)
    season = np.array([1, 1, 1, 1, 1, .98, .93, .9, 1, 1, .98, .88])[np.arange(months) % 12]

    # weekday / weekend shapes (dow 0..6) -> [dow][hour] pairs for the AM-direction and PM-direction
    dowamp = np.array([.85, 1.0, 1.04, 1.0, .92, 0, 0])
    stations = []
    for fwy, (dirs, pts, i0, i1) in FWYS.items():
        stations += stations_along(fwy, dirs, pts, (i0, i1))
    stations.sort(key=lambda s: (s["fwy"], s["dir"], s["pm"]))
    for i, s in enumerate(stations):
        s["id"] = 400000 + i

    # per (fwy,dir): bottlenecks along the corridor
    bott = {}
    for s in stations:
        k = (s["fwy"], s["dir"])
        if k not in bott:
            nb = rng.integers(3, 6)
            bott[k] = [(rng.uniform(0.05, 0.95), rng.uniform(0.03, 0.08), rng.uniform(0.5, 1.0)) for _ in range(nb)]
            # a long-running construction/bottleneck "event" along part of the corridor
            bott[k].append(("evt", rng.uniform(0.1, 0.9), rng.integers(30, 90), rng.integers(12, 30)))

    n = len(stations)
    cube = np.full((n, months, 7, SPD), 255, dtype=np.uint8)
    mon_idx = np.arange(months)
    for i, s in enumerate(stations):
        k = (s["fwy"], s["dir"])
        loc = 0.30
        evt = np.zeros(months)
        for b in bott[k]:
            if b[0] == "evt":
                if abs(s["frac"] - b[1]) < 0.08:
                    evt[b[2]:b[2] + b[3]] = 0.5
            else:
                loc += b[2] * math.exp(-0.5 * ((s["frac"] - b[0]) / b[1]) ** 2)
        ff = rng.uniform(63, 71)
        drift = rng.normal(0, 0.012)               # per-station slow trend
        am = s["am"] * np.exp(-0.5 * ((hours - 7.9) / 1.0) ** 2) + 0.18 * s["am"] * np.exp(-0.5 * ((hours - 12.5) / 2.0) ** 2)
        pm = s["pm_int"] * np.exp(-0.5 * ((hours - 17.0) / 1.45) ** 2) + 0.15 * s["pm_int"] * np.exp(-0.5 * ((hours - 12.5) / 2.0) ** 2)
        wk = (am + pm)                            # [slot]
        wkend = 0.35 * np.exp(-0.5 * ((hours - 14.0) / 2.6) ** 2) * (s["am"] + s["pm_int"]) / 2
        sev = np.zeros((months, 7, SPD))
        demand = yf * season * (1 + drift * (mon_idx / 12.0 - 5)) + evt
        for d in range(7):
            base = wk * dowamp[d] if d < 5 else wkend * (1.0 if d == 5 else 0.8)
            sev[:, d, :] = demand[:, None] * loc * base[None, :]
        speed = ff * (1 - 0.82 * (1 - np.exp(-1.6 * sev)))      # saturating drop
        speed += rng.normal(0, 1.2, speed.shape)
        cube[i] = np.clip(np.rint(speed), 5, 80).astype(np.uint8)
        # simulate sensor outages
        if rng.random() < 0.08:
            a = rng.integers(0, months - 6)
            cube[i, a:a + rng.integers(2, 6)] = 255

    write_dataset(out_dir, stations, cube, START_YEAR, SLOT_MIN,
                  "SYNTHETIC demo data (not real traffic)", synthetic=True)


if __name__ == "__main__":
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
    main(os.path.abspath(root))
