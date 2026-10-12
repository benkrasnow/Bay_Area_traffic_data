"""Sampling plan for the PeMS 5-minute daily files, plus a download tracker.

    python tools/plan_sample.py plan   [--start 2016-10] [--end 2026-09] [--seed 1]
    python tools/plan_sample.py status [folder]            # what is downloaded / still missing

'plan' writes sampling_plan.csv: one row per day to download, in three nested passes.
  pass 1  "lean"         ~36 files / year   (every other month on weekdays, 3 months a year on weekends)
  pass 2  "recommended"  +36 -> 72 / year   (every month once per weekday; every other month on weekends)
  pass 3  "rich"         +72 -> 144 / year  (a second date per weekday every month; weekends monthly)
Column 'xlean' marks an "extra lean" subset (~18 files / year, ~180 total, ~5.4 GB) chosen from passes 1-2:
every weekday 3 times per block of 12 months, weekends 1-2 times, spread over the seasons.
Download order: xlean first, then the rest of passes 1-2 (xlean files are never wasted), then pass 3.
Download pass 1 for all years first, then pass 2 (and 3 if you want): every stage is balanced by itself.
Holidays and the days around them (see calendar_rules.py) are never chosen.
Each row also lists two backup dates (same weekday, same month) in case a file is missing on PeMS.
"""
import argparse
import csv
import datetime as dt
import glob
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from calendar_rules import is_excluded, reason  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
MB_PER_FILE = 30
PLAN_CSV = os.path.join(ROOT, "sampling_plan.csv")
DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def fname(d):
    return f"d04_text_station_5min_{d:%Y_%m_%d}.txt.gz"


def pass_of(month, weekend, rank):
    if weekend:
        return 1 if month in (1, 5, 9) else 2 if month in (3, 7, 11) else 3
    return 3 if rank == 2 else (1 if month % 2 else 2)


def select_xlean(rows, sy, sm, ey, em, seed):
    """Pick the extra-lean subset (xlean=1) from rows with pass <= 2. One 12-month block (starting at the
    plan's start month) at a time: 15 weekday dates (3 per weekday, every month covered, weekday-to-month
    pairing rotated between blocks) + 3 weekend dates (Sat, Sun, and one extra alternating Sat/Sun)."""
    by = {(r[1][:7], r[2]): r for r in rows if r[0] <= 2}
    months = []
    y, m = sy, sm
    while (y, m) <= (ey, em):
        months.append((y, m))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    chosen = set()
    for b in range(len(months) // 12):
        rng = random.Random(f"{seed}-xlean-{b}")
        blk = months[b * 12:(b + 1) * 12]
        wk = {d: [] for d in range(5)}                 # weekday -> month indexes within the block
        off = (2 * b) % 5
        for i in range(12):                            # cycle weekdays over the months (one date per month)
            wk[(i + off) % 5].append(i)
        order = list(range(12))
        rng.shuffle(order)
        for d in [d for d in range(5) if len(wk[d]) < 3]:     # top up the weekdays that got only 2
            i = next(i for i in order if i not in wk[d] and sum(i in v for v in wk.values()) < 2)
            wk[d].append(i)
        for d, idxs in wk.items():
            for i in idxs:
                key = (f"{blk[i][0]}-{blk[i][1]:02d}", DOW[d])
                if key in by:
                    chosen.add(by[key][1])
        odd = [i for i in range(12) if blk[i][1] % 2 == 1]       # weekend rows exist in odd calendar months
        rng.shuffle(odd)
        extra_dn = "Sat" if b % 2 == 0 else "Sun"
        picks = [(odd[0], "Sat"), (odd[3], "Sun"), (odd[1] if b % 2 == 0 else odd[2], extra_dn)]
        for i, dn in picks:
            key = (f"{blk[i][0]}-{blk[i][1]:02d}", dn)
            if key in by:
                chosen.add(by[key][1])
    return chosen


def month_days(y, m, last):
    d = dt.date(y, m, 1)
    while d.month == m and d <= last:
        yield d
        d += dt.timedelta(1)


def plan(args):
    sy, sm = map(int, args.start.split("-"))
    ey, em = map(int, args.end.split("-"))
    last = min(dt.date.today() - dt.timedelta(3), (dt.date(ey + (em == 12), em % 12 + 1, 1) - dt.timedelta(1)))
    rows = []
    y, m = sy, sm
    short = []
    while (y, m) <= (ey, em):
        rng = random.Random(f"{args.seed}-{y}-{m}")
        cand = {d: [x for x in month_days(y, m, last) if x.weekday() == d and not is_excluded(x)] for d in range(7)}
        chosen = {}                                    # (dow, rank) -> date
        used_weeks = {1: set(), 2: set()}
        for rank in (1, 2):
            order = list(range(5))
            rng.shuffle(order)
            for d in order:                            # weekdays: spread over different weeks of the month
                pool = [x for x in cand[d] if x not in chosen.values()]
                if not pool:
                    short.append((y, m, DOW[d], rank))
                    continue
                fresh = [x for x in pool if x.isocalendar()[1] not in used_weeks[rank]]
                pick = rng.choice(fresh or pool)
                used_weeks[rank].add(pick.isocalendar()[1])
                chosen[(d, rank)] = pick
        for d in (5, 6):                               # weekends: one date per month
            pool = cand[d]
            if pool:
                chosen[(d, 1)] = rng.choice(pool)
            else:
                short.append((y, m, DOW[d], 1))
        for (d, rank), day in sorted(chosen.items(), key=lambda kv: kv[1]):
            backups = [x for x in cand[d] if x not in chosen.values()]
            rng.shuffle(backups)
            rows.append([pass_of(m, d >= 5, rank), day.isoformat(), DOW[d], fname(day)] +
                        [b.isoformat() for b in backups[:2]] + [""] * (2 - len(backups[:2])))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    rows.sort(key=lambda r: (r[0], r[1]))
    xl = select_xlean(rows, sy, sm, ey, em, args.seed)
    for r in rows:
        r.append(1 if r[1] in xl else 0)
    with open(PLAN_CSV, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["pass", "date", "dow", "filename", "backup1", "backup2", "xlean"])
        w.writerows(rows)
    print(f"wrote {PLAN_CSV}")
    summarize(rows)
    if short:
        print("note: no eligible date for", ", ".join(f"{a}-{b:02d} {c}#{r}" for a, b, c, r in short[:12]),
              "..." if len(short) > 12 else "")


def summarize(rows):
    months = len({r[1][:7] for r in rows})
    print(f"\n{'pass':<22}{'files':>7}{'cumulative':>12}{'size (GB)':>11}")
    nx = sum(1 for r in rows if r[-1] == 1)
    print(f"{'xlean (subset of 1-2)':<22}{nx:>7}{nx:>12}{nx * MB_PER_FILE / 1000:>11.1f}")
    cum = 0
    for p, name in ((1, "1 lean"), (2, "2 recommended"), (3, "3 rich")):
        n = sum(1 for r in rows if r[0] == p)
        cum += n
        print(f"{name:<22}{n:>7}{cum:>12}{cum * MB_PER_FILE / 1000:>11.1f}")
    print(f"({months} months covered; assumes ~{MB_PER_FILE} MB per file)")


def load_plan():
    if not os.path.exists(PLAN_CSV):
        sys.exit("No sampling_plan.csv yet; run:  python tools/plan_sample.py plan")
    with open(PLAN_CSV, newline="") as f:
        return list(csv.DictReader(f))


def status(args):
    rows = load_plan()
    have = {os.path.basename(p) for p in glob.glob(os.path.join(args.folder, "**", "*station_5min_*"), recursive=True)}
    cache = {os.path.basename(p).replace(".npz", "") for p in glob.glob(os.path.join(ROOT, "pems_cache", "*.npz"))}

    def got(day_iso):
        d = dt.date.fromisoformat(day_iso)
        n = fname(d)
        return n in have or n.replace(".txt.gz", "") in cache

    stats = {}
    missing = []
    for r in rows:
        ok = got(r["date"]) or any(r[b] and got(r[b]) for b in ("backup1", "backup2"))
        keys = [int(r["pass"])] + (["xlean"] if r.get("xlean") == "1" else [])
        for k in keys:
            s = stats.setdefault(k, [0, 0])
            s[1] += 1
            s[0] += ok
        if not ok:
            missing.append(r)
    print(f"{'set':<8}{'have':>6}{'of':>6}{'missing':>9}{'GB left':>9}")
    for p in sorted(stats, key=str):
        h, t = stats[p]
        print(f"{p:<8}{h:>6}{t:>6}{t - h:>9}{(t - h) * MB_PER_FILE / 1000:>9.1f}")
    if args.write:
        missing.sort(key=lambda r: (r.get("xlean") != "1", r["pass"], r["date"]))
    if args.write and missing:
        out = os.path.join(ROOT, "missing_files.txt")
        with open(out, "w") as f:
            for r in missing:
                f.write(f"pass{r['pass']}\t{r['date']}\t{r['dow']}\t{r['filename']}\n")
        print("listed remaining files in", out)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--start", default="2016-10")
    p.add_argument("--end", default="2026-09")
    p.add_argument("--seed", type=int, default=1)
    s = sub.add_parser("status")
    s.add_argument("folder", nargs="?", default=ROOT)
    s.add_argument("--write", action="store_true", help="write missing_files.txt")
    a = ap.parse_args()
    plan(a) if a.cmd == "plan" else status(a)


if __name__ == "__main__":
    main()
