"""Which calendar days are atypical for commute traffic and should be excluded from 'typical week' averages.

Excluded: US federal holidays + California's Cesar Chavez Day (observed dates too) with a buffer around
them (day before / after, and the Friday/Saturday ahead of a Monday holiday, the weekend after a Friday
holiday), the whole Thanksgiving Wed-Sun, the Christmas / New Year school break (Dec 22 - Jan 2),
and Good Friday / Easter Sunday.  Edit here to change the rules; both the sampling plan
(plan_sample.py) and the data processor (pems_to_app.py) use this one file.
"""
import datetime as dt
from functools import lru_cache

D = dt.timedelta


def nth_weekday(y, m, wd, n):
    """n-th (1-based) weekday wd (Mon=0) of month, or last if n == -1."""
    if n > 0:
        d = dt.date(y, m, 1)
        d += D((wd - d.weekday()) % 7 + 7 * (n - 1))
        return d
    d = dt.date(y + (m == 12), m % 12 + 1, 1) - D(1)
    return d - D((d.weekday() - wd) % 7)


def easter(y):
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mo, da = divmod(h + l - 7 * m + 114, 31)
    return dt.date(y, mo, da + 1)


def observed(d):
    """Federal 'observed' date: Saturday -> Friday, Sunday -> Monday."""
    return d - D(1) if d.weekday() == 5 else d + D(1) if d.weekday() == 6 else d


@lru_cache(None)
def holidays(y):
    h = {
        dt.date(y, 1, 1): "New Year's Day",
        nth_weekday(y, 1, 0, 3): "Martin Luther King Jr. Day",
        nth_weekday(y, 2, 0, 3): "Presidents' Day",
        dt.date(y, 3, 31): "Cesar Chavez Day",
        nth_weekday(y, 5, 0, -1): "Memorial Day",
        dt.date(y, 7, 4): "Independence Day",
        nth_weekday(y, 9, 0, 1): "Labor Day",
        nth_weekday(y, 10, 0, 2): "Columbus / Indigenous Peoples' Day",
        dt.date(y, 11, 11): "Veterans Day",
        nth_weekday(y, 11, 3, 4): "Thanksgiving",
        dt.date(y, 12, 25): "Christmas Day",
    }
    if y >= 2021:
        h[dt.date(y, 6, 19)] = "Juneteenth"
    return h


@lru_cache(None)
def excluded_days(y):
    """{date: reason} for every excluded day whose date falls in calendar year y."""
    out = {}

    def add(d, why):
        out.setdefault(d, why)

    for yy in (y - 1, y, y + 1):                      # holidays near a year boundary spill over
        for hd, name in holidays(yy).items():
            for d in {hd, observed(hd)}:
                for k in (-1, 0, 1):
                    add(d + D(k), name)
                if d.weekday() == 0:                   # long weekend: Fri, Sat, Sun before
                    add(d - D(3), name)
                    add(d - D(2), name)
                if d.weekday() == 4:                   # Friday holiday: weekend after
                    add(d + D(2), name)
        tg = holidays(yy)
        thanks = [d for d, n in tg.items() if n == "Thanksgiving"][0]
        for k in range(-1, 4):                         # Wed .. Sun
            add(thanks + D(k), "Thanksgiving week")
        for k in range(-3, 9):                         # Dec 22 .. Jan 2
            add(dt.date(yy, 12, 25) + D(k), "Winter break")
        e = easter(yy)
        add(e - D(2), "Good Friday")
        add(e, "Easter Sunday")
    return {d: w for d, w in out.items() if d.year == y}


def is_excluded(d):
    return d in excluded_days(d.year)


def reason(d):
    return excluded_days(d.year).get(d)


if __name__ == "__main__":
    import sys
    y = int(sys.argv[1]) if len(sys.argv) > 1 else dt.date.today().year
    for d in sorted(excluded_days(y)):
        print(d, d.strftime("%a"), excluded_days(y)[d])
    print(len(excluded_days(y)), "excluded days in", y)
