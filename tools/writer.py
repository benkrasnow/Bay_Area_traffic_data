"""Shared writer: turns an aggregated speed cube into the files the web app reads.

Input cube: uint8 array [station][month][dow][slot]  (mph, 255 = missing)
  month 0 = January of start_year, dow 0 = Monday, slot = time-of-day bucket.
  Stations must be sorted by (freeway, direction, postmile).

Output (in out_dir), all pre-compressed (the page unzips them itself):
  meta.json                 sizes, resolution, and where each corridor sits in the station list
  stations.json             detector list (only when write_stations=True)
  map_<year>.bin.gz         [dow][slot][station] yearly averages, map resolution (e.g. 5 min)
  hist/<fwy><dir>.bin.gz    one file per freeway direction: every detector's [month][dow][slot] history, stored at
                            a coarser resolution (hist_slot_minutes, default 15 min) and concatenated in station order
"""
import gzip
import json
import os
import shutil

import numpy as np

MISSING = 255


def _rebin(sub, f):
    """[k, months, 7, spd] uint8 -> [k, months, 7, spd/f], averaging the valid values in each group of f slots."""
    if f == 1:
        return sub
    k, m, d, s = sub.shape
    r = sub.reshape(k, m, d, s // f, f).astype(np.float32)
    ok = r != MISSING
    cnt = ok.sum(axis=4)
    tot = np.where(ok, r, 0).sum(axis=4)
    mean = np.where(cnt > 0, tot / np.maximum(cnt, 1), MISSING)
    return np.rint(mean).astype(np.uint8)


def _gz(b):
    return gzip.compress(b, 9, mtime=0)


def write_dataset(out_dir, stations, cube, start_year, slot_minutes, source, synthetic=False,
                  write_stations=True, hist_slot_minutes=15):
    """stations: list of dicts (id,fwy,dir,lat,lon,pm,lanes), sorted by (fwy,dir,pm)."""
    n, months, ndow, spd = cube.shape
    assert ndow == 7 and spd == 1440 // slot_minutes
    hist = max(slot_minutes, hist_slot_minutes)
    if hist % slot_minutes:
        raise ValueError("hist_slot_minutes must be a multiple of slot_minutes")
    f = hist // slot_minutes

    os.makedirs(out_dir, exist_ok=True)
    for name in os.listdir(out_dir):                      # clear old output (including older layouts)
        path = os.path.join(out_dir, name)
        if os.path.isfile(path) and name.startswith("map_"):
            os.remove(path)
    for sub in ("st", "hist"):
        shutil.rmtree(os.path.join(out_dir, sub), ignore_errors=True)
    os.makedirs(os.path.join(out_dir, "hist"))

    # free-flow speed = 90th percentile of all observed values, clipped to a sane range
    # (reused if the stations already carry one, e.g. when writing the second dataset)
    if not all("ff" in s for s in stations):
        valid = cube != MISSING
        for i, s in enumerate(stations):
            v = cube[i][valid[i]]
            s["ff"] = int(round(float(np.clip(np.percentile(v, 90), 45, 75)))) if v.size else 65

    if write_stations:
        rows = [[s["id"], s["fwy"], s["dir"], round(s["lat"], 5), round(s["lon"], 5),
                 round(s["pm"], 3), s.get("lanes", 0), s["ff"]] for s in stations]
        with open(os.path.join(out_dir, "stations.json"), "w") as fh:
            json.dump({"fields": ["id", "fwy", "dir", "lat", "lon", "pm", "lanes", "ff"], "rows": rows},
                      fh, separators=(",", ":"))

    nyears = (months + 11) // 12
    for y in range(nyears):
        sub = cube[:, y * 12:(y + 1) * 12].astype(np.float32)
        ok = sub != MISSING
        cnt = ok.sum(axis=1)                              # [st][dow][slot]
        tot = np.where(ok, sub, 0).sum(axis=1)
        mean = np.where(cnt > 0, tot / np.maximum(cnt, 1), MISSING)
        out = np.rint(mean).astype(np.uint8).transpose(1, 2, 0)      # [dow][slot][st]
        with open(os.path.join(out_dir, f"map_{start_year + y}.bin.gz"), "wb") as fh:
            fh.write(_gz(np.ascontiguousarray(out).tobytes()))

    corridors, a, seen = {}, 0, set()                     # one history file per (freeway, direction)
    while a < n:
        key = (stations[a]["fwy"], stations[a]["dir"])
        b = a
        while b < n and (stations[b]["fwy"], stations[b]["dir"]) == key:
            b += 1
        assert key not in seen, "stations must be sorted by (fwy, dir, pm)"
        seen.add(key)
        name = f"{key[0]}{key[1]}"
        data = _rebin(cube[a:b], f)
        with open(os.path.join(out_dir, "hist", f"{name}.bin.gz"), "wb") as fh:
            fh.write(_gz(np.ascontiguousarray(data).tobytes()))
        corridors[name] = [a, b - a]
        a = b

    with open(os.path.join(out_dir, "meta.json"), "w") as fh:
        json.dump({"slotMinutes": slot_minutes, "slotsPerDay": spd, "startYear": start_year,
                   "months": months, "stations": n, "source": source, "synthetic": synthetic,
                   "hist": {"slotMinutes": hist, "slotsPerDay": 1440 // hist, "corridors": corridors}},
                  fh, separators=(",", ":"))
    print(f"wrote {n} stations, {months} months, {spd} slots/day (history {1440 // hist}/day, "
          f"{len(corridors)} corridors) -> {out_dir}")
