"""Convert downloaded Caltrans PeMS files into the data folders used by index.html.

What to download from https://pems.dot.ca.gov  (free account)  ->  Data Clearinghouse:
  * Type "Station Hourly" (or "Station 5-Minute"), District 4, every month/day you want.
    Files look like  d04_text_station_hour_2019_03.txt.gz   (or  ..._station_5min_2019_03_14.txt.gz)
  * Type "Station Metadata", District 4: one file like  d04_text_meta_2019_03_16.txt
    (use the newest one; it lists lat/lon, freeway, direction, postmile for each detector)
Put them all (any sub-folders are fine) under one folder, then:

    python tools/pems_to_app.py  <folder>  [--out data] [--slot-minutes 5]

Two datasets are written:
  data/       measured values only      (samples that PeMS marks >= 50% observed)
  data/est/   measured + PeMS-estimated (PeMS fills in readings for detectors that are down and marks them
              0% observed; the app can show these via its "include PeMS estimates" switch)
Both use the same detector list/order, so the app can swap between them.
Each sample is averaged per (station, month, day-of-week, time-slot).  Only needs numpy.
"""
import argparse
import csv
import glob
import gzip
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from calendar_rules import is_excluded  # noqa: E402
from writer import write_dataset  # noqa: E402

CACHE_VERSION = 2          # 2: per-file cache holds both measured-only and measured+estimated sums


def open_any(path):
    return gzip.open(path, "rt", newline="") if path.endswith(".gz") else open(path, newline="")


def load_meta(folder):
    files = sorted(glob.glob(os.path.join(folder, "**", "*meta*.txt*"), recursive=True))
    if not files:
        sys.exit("No station metadata file (d04_text_meta_*.txt) found.")
    path = files[-1]
    print("metadata:", path)
    st = {}
    with open_any(path) as f:
        rd = csv.reader(f, delimiter="\t")
        hdr = [h.strip().lower() for h in next(rd)]
        col = {h: i for i, h in enumerate(hdr)}
        for r in rd:
            try:
                if r[col["type"]] != "ML":              # mainline detectors only
                    continue
                lat, lon = float(r[col["latitude"]]), float(r[col["longitude"]])
                st[int(r[col["id"]])] = dict(id=int(r[col["id"]]), fwy=int(r[col["fwy"]]), dir=r[col["dir"]],
                                             lat=lat, lon=lon, pm=float(r[col["abs_pm"]]),
                                             lanes=int(r[col["lanes"]] or 0))
            except (ValueError, IndexError, KeyError):
                continue
    print(len(st), "mainline stations in metadata")
    return st


def native_res(path):
    """Time resolution (minutes) of a raw file, from its name."""
    n = os.path.basename(path)
    if "5min" in n:
        return 5
    if "hour" in n:
        return 60
    sys.exit(f"Don't know the resolution of {n} (expected station_5min or station_hour).")


def file_month(name):
    """Absolute month index (year*12+month0) from a PeMS file name like ..._2019_03_14.txt.gz"""
    m = re.search(r"_(20\d\d)_(\d\d)", os.path.basename(name))
    return int(m.group(1)) * 12 + int(m.group(2)) - 1


def aggregate_file(path, res, min_obs, skip_holidays):
    """One raw file -> {(station_id, abs_month): [sum_obs, cnt_obs, sum_all, cnt_all]} (each (7, spd)),
    at the file's native resolution.  'obs' = measured samples only; 'all' = measured + PeMS-estimated."""
    import datetime
    spd = 1440 // res
    acc, dows = {}, {}
    with open_any(path) as f:
        for r in csv.reader(f):
            try:
                if r[5] != "ML" or r[11] == "":
                    continue
                ts = r[0]                                  # MM/DD/YYYY HH:MM:SS
                day = ts[:10]
                if day not in dows:
                    dd = datetime.date(int(ts[6:10]), int(ts[0:2]), int(ts[3:5]))
                    dows[day] = -1 if (skip_holidays and is_excluded(dd)) else dd.weekday()
                if dows[day] < 0:
                    continue
                key = (int(r[1]), int(ts[6:10]) * 12 + int(ts[0:2]) - 1)
                a = acc.get(key)
                if a is None:
                    a = acc[key] = [np.zeros((7, spd), np.float32), np.zeros((7, spd), np.uint16),
                                    np.zeros((7, spd), np.float32), np.zeros((7, spd), np.uint16)]
                slot = (int(ts[11:13]) * 60 + int(ts[14:16])) // res
                v = float(r[11])
                d = dows[day]
                a[2][d, slot] += v
                a[3][d, slot] += 1
                if r[8] == "" or float(r[8]) >= min_obs:    # measured, not estimated
                    a[0][d, slot] += v
                    a[1][d, slot] += 1
            except (ValueError, IndexError):
                continue
    return acc


def cache_name(path):
    return os.path.basename(path).replace(".txt.gz", "").replace(".txt", "") + ".npz"


def cache_ok(cpath, skip_holidays):
    if not os.path.exists(cpath):
        return False
    z = np.load(cpath)
    return ("version" in z and int(z["version"]) == CACHE_VERSION and
            bool(z["holidays_skipped"]) == skip_holidays)


def build_cache(path, cache_dir, min_obs, skip_holidays):
    cpath = os.path.join(cache_dir, cache_name(path))
    if cache_ok(cpath, skip_holidays):
        return cpath
    res = native_res(path)
    acc = aggregate_file(path, res, min_obs, skip_holidays)
    keys = list(acc)
    spd = 1440 // res

    def stack(j, dt):
        return np.stack([acc[k][j] for k in keys]) if keys else np.zeros((0, 7, spd), dt)

    os.makedirs(cache_dir, exist_ok=True)
    np.savez_compressed(cpath, version=CACHE_VERSION, res=res, holidays_skipped=np.array(skip_holidays),
                        ids=np.array([k[0] for k in keys], np.int32), mos=np.array([k[1] for k in keys], np.int32),
                        sums=stack(0, np.float32), cnts=stack(1, np.uint16),
                        sums_all=stack(2, np.float32), cnts_all=stack(3, np.uint16))
    return cpath


def rebin(arr, res, target):
    """[n,7,1440/res] -> [n,7,1440/target]. Finer->coarser sums bins; coarser->finer repeats the value."""
    if res == target:
        return arr
    if res < target:
        if target % res:
            sys.exit(f"--slot-minutes {target} is not a multiple of {res}")
        return arr.reshape(arr.shape[0], 7, 1440 // target, target // res).sum(axis=3, dtype=arr.dtype)
    if res % target:
        sys.exit(f"--slot-minutes {target} does not divide {res}")
    return np.repeat(arr, res // target, axis=2)


def build_cube(kind, cpaths, fine_months, index, nst, y0, months, slot_minutes):
    """Accumulate every cached file into one [station][month][dow][slot] uint8 cube. kind: 'obs' or 'all'."""
    spd = 1440 // slot_minutes
    ssum = np.zeros((nst, months, 7, spd), dtype=np.float32)
    scnt = np.zeros((nst, months, 7, spd), dtype=np.uint16)
    sk, ck = ("sums", "cnts") if kind == "obs" else ("sums_all", "cnts_all")
    for cp in cpaths:
        z = np.load(cp)
        res = int(z["res"])
        ids, mos = z["ids"], z["mos"]
        keep = np.array([int(i) in index for i in ids], bool)
        if res >= 60 and fine_months.size:                 # coarse data in months that have 5-min days: skip
            keep &= ~np.isin(mos, fine_months)
        if not keep.any():
            continue
        ks = np.array([index[int(i)] for i in ids[keep]])
        mo = mos[keep] - y0 * 12
        ssum[ks, mo] += rebin(z[sk][keep], res, slot_minutes)
        scnt[ks, mo] += rebin(z[ck][keep].astype(np.uint32), res, slot_minutes).astype(np.uint16)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = ssum / np.maximum(scnt, 1)
    cube = np.clip(np.rint(mean), 1, 120).astype(np.uint8)
    cube[scnt == 0] = 255
    return cube


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data"))
    ap.add_argument("--cache", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pems_cache"),
                    help="per-file summaries; once a raw file is cached you may delete it")
    ap.add_argument("--slot-minutes", type=int, default=60,
                    help="output time resolution: 5, 10, 15, 30 or 60. Hourly source files are repeated into finer slots.")
    ap.add_argument("--min-observed", type=float, default=50,
                    help="a sample counts as 'measured' when at least this %% was observed (rest are PeMS estimates)")
    ap.add_argument("--keep-holidays", action="store_true",
                    help="do NOT exclude holidays and the days around them (see tools/calendar_rules.py)")
    ap.add_argument("--delete-raw", action="store_true", help="delete each raw data file after it is cached")
    a = ap.parse_args()
    skip_holidays = not a.keep_holidays
    meta = load_meta(a.folder)

    files = sorted(p for p in glob.glob(os.path.join(a.folder, "**", "*station_*"), recursive=True)
                   if "meta" not in p and not p.endswith(".npz"))
    existing = glob.glob(os.path.join(a.cache, "*.npz"))
    if not files and not existing:
        sys.exit("No station_hour / station_5min data files found.")
    for n, p in enumerate(files):
        print(f"[{n + 1}/{len(files)}] {os.path.basename(p)}", flush=True)
        build_cache(p, a.cache, a.min_observed, skip_holidays)
        if a.delete_raw:
            os.remove(p)
    cpaths = sorted(glob.glob(os.path.join(a.cache, "*.npz")))
    bad = [c for c in cpaths if not cache_ok(c, skip_holidays)]
    if bad:
        sys.exit(f"{len(bad)} cached files are from an older version or holiday setting and their raw files are gone "
                 f"(e.g. {os.path.basename(bad[0])}). Re-download them or delete those cache files.")

    mo_all = [file_month(c) for c in cpaths]
    fine_months = np.array(sorted({file_month(c) for c in cpaths if "5min" in os.path.basename(c)}), dtype=np.int64)
    y0, y1 = min(mo_all) // 12, max(mo_all) // 12
    months = (y1 - y0 + 1) * 12
    ids = sorted(meta, key=lambda i: (meta[i]["fwy"], meta[i]["dir"], meta[i]["pm"]))
    index = {sid: k for k, sid in enumerate(ids)}
    nst = len(ids)
    need = nst * months * 7 * (1440 // a.slot_minutes) * 6 / 1e9
    if need > 6:
        sys.exit(f"At {a.slot_minutes}-minute resolution this needs ~{need:.0f} GB of RAM; use a coarser --slot-minutes.")

    print("building measured + estimated cube ...", flush=True)
    cube_all = build_cube("all", cpaths, fine_months, index, nst, y0, months, a.slot_minutes)
    have = (cube_all != 255).reshape(nst, -1).mean(axis=1) > 0.02          # drop detectors with almost no data at all
    keep = [i for i in range(nst) if have[i]]
    cube_all = cube_all[keep]
    print("building measured-only cube ...", flush=True)
    cube_obs = build_cube("obs", cpaths, fine_months, index, nst, y0, months, a.slot_minutes)[keep]
    stations = [meta[ids[i]] for i in keep]

    out = os.path.abspath(a.out)
    src = "Caltrans PeMS (pems.dot.ca.gov), District 4"
    write_dataset(out, stations, cube_obs, y0, a.slot_minutes, src + " - measured values only")
    write_dataset(os.path.join(out, "est"), stations, cube_all, y0, a.slot_minutes,
                  src + " - measured + PeMS-estimated values", write_stations=False)


if __name__ == "__main__":
    main()
