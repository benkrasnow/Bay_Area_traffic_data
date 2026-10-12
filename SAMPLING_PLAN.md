# Sampling plan for 5-minute PeMS data

Generate / refresh the list: `python tools/plan_sample.py plan` -> `sampling_plan.csv`
Track progress:              `python tools/plan_sample.py status --write` -> `missing_files.txt`
Process downloads:           `python tools/pems_to_app.py . --slot-minutes 5 --delete-raw`

## Measured variability (from the 30 days of Sept 2026 hourly data)
Day-to-day standard deviation of speed at the same detector, weekday and hour:

| Cells | median SD |
|---|---|
| congested (mean < 45 mph) | 9.8 mph (p90 14) |
| free-flow (> 60 mph) | 1.3 mph |
| weekends, all cells | 0.7 mph |

Congested weekday peaks are the only place sampling error matters. Standard error of an average of n days = SD / sqrt(n).

## Tiers (nested; 10 years = Oct 2016 - Sep 2026)

| Pass | Weekday dates | Weekend dates | Files/yr | Cumulative files | Cumulative size |
|---|---|---|---|---|---|
| 1 lean | each weekday, odd months | Sat+Sun in Jan, May, Sep | 36 | 360 | ~10.8 GB |
| 2 recommended | + even months | + Mar, Jul, Nov | 72 | 720 | ~21.6 GB |
| 3 rich | + a 2nd date each month | + remaining months | 144 | 1,440 | ~43 GB |

| | days per weekday per year | SE at a congested peak, one point, one weekday, one year | SE Mon-Fri average | smallest year-to-year change detectable* |
|---|---|---|---|---|
| lean | 6 | 4.1 mph | 1.8 | ~11 mph |
| recommended | 12 | 2.9 mph | 1.3 | ~8 mph |
| rich | 24 | 2.0 mph | 0.9 | ~5.6 mph |

*95% confidence, single detector at a congested peak. Averaging several years, several detectors or a whole corridor is much tighter. Free-flow and weekend cells are accurate with a single day.

## Extra lean (xlean): 180 files, ~5.4 GB
A subset of passes 1-2 (marked `xlean=1` in sampling_plan.csv), so nothing is wasted if you upgrade later.
Per 12-month block (Oct-Sep): every weekday exactly 3 times, Sat/Sun 1-2 times each (alternating), every month
of the year represented, and the weekday-to-month pairing rotated from block to block so each calendar month
gets all weekdays over the decade (Tue-Thu: 6-9 samples per calendar month in 10 years).

| Estimate | days averaged | SE at a congested peak (SD 10 mph) |
|---|---|---|
| one weekday, one year, one detector | 3 | 5.8 mph (noisy) |
| **Tue-Thu pooled, one year** | 9 | 3.3 mph |
| Mon-Fri pooled, one year | 15 | 2.6 mph |
| one weekday, 3-year range | 9 | 3.3 mph |
| weekends | 1-2 | <= 0.7 mph |

Use it for: regional/corridor trends, typical patterns over year ranges, COVID-scale shifts (15+ mph). Weak for:
a single weekday at a single detector in a single year, or subtle year-to-year changes (smallest detectable at one
detector, one weekday: ~16 mph; Tue-Thu pooled: ~9 mph). Tuesday, Wednesday and Thursday behave almost identically
(Sept 2026: 30.4 / 30.8 / 32.0 mph at 8am on congested detectors), so the app has a pooled **Tue-Thu** option
that triples the sample; Monday and Friday are different and stay separate.

Order: xlean (180) -> rest of passes 1-2 (540 more) -> pass 3.

## Rules
- Holidays excluded (tools/calendar_rules.py): federal holidays + Cesar Chavez Day, observed dates, +/-1 day, the Fri-Sun before a Monday holiday, Thanksgiving Wed-Sun, Dec 22 - Jan 2, Good Friday, Easter Sunday.
- The processor applies the same rule to any file, so full-month files do not smuggle holidays in (use `--keep-holidays` to override).
- Within a month, weekdays are spread across different weeks (avoids one rainy / incident week dominating).
- Dates are random within those constraints (seeded), not "first Tuesday", so day-of-month effects average out.
- Two backup dates per target, same weekday and month, if PeMS is missing the file.
- In months where 5-minute days exist, any hourly data for that month is ignored (no double counting).
