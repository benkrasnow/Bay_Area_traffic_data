# Bay Area Traffic Trends

An interactive map of **typical** Bay Area freeway traffic, built from ten years of Caltrans PeMS detector data
(District 4, Oct 2016 – Sep 2026). Instead of "what is traffic like right now", it answers questions like
*"what does an average Tuesday at 8 am look like?"*, *"how has the 101 evening commute changed since 2018?"* and
*"where is the commute lopsided?"*

It is a static web app: one `index.html` plus a `data/` folder. No server code, no database.

## What it does
- **Map** — color-coded typical speed for a chosen day (Mon…Sun, Tue–Thu, Mon–Fri, Sat–Sun), time of day (5-minute
  steps, with an animation), and range of years (drag the timeline handles or slide the whole range). Each direction of
  a freeway is drawn side by side. Colors run from dark red (30 mph or less) to green (65+ mph).
- **Point** — click a freeway: speed through the day (or week) for both directions, the same time of week across the
  years (dots plus a robust smoothed trend with an uncertainty band), and a day-by-hour heatmap. Drag on the
  "through the day" graph to scrub the time.
- **Corridor** — time-space diagrams (where and when queues form) and hours of congestion per day over the years.
- **Route** — travel time by departure time between two points, both directions.
- **Asymmetry** — recolors the map by how lopsided the morning and evening commutes are between the two directions
  (area above the speed curve, in mph·hours).
- **Compare** — change in speed versus another year.
- **Region** — share of freeway that is congested by year, slowest spots, biggest changes.
- **Include PeMS estimates** switch — PeMS itself is missing data from many detectors that fail or go offline; it
  fills those gaps with estimates. By default only real measurements are shown.

## Run it locally
Browsers block local file access, so serve the folder:

```bash
python -m http.server 8000
```

then open <http://localhost:8000>. It needs an internet connection for the map tiles and the Leaflet / Chart.js
libraries (loaded from CDNs). A recent Chrome, Edge, Firefox or Safari is required (the page unzips its own data).

## Put it on GitHub Pages
Everything the page needs is `index.html`, `data/` and the empty `.nojekyll` file (about 70 MB, 141 files).

1. Create a repository and commit (the `.gitignore` already leaves out the multi-GB raw downloads and caches).
2. *Settings → Pages → Deploy from a branch → main / (root).*
3. Visitors download about 20 MB the first time (the yearly map files); each freeway's history loads when it is first
   clicked (about 1–2 MB). Turning on the PeMS-estimates switch downloads about 22 MB more.

Commit the data folder once and regenerate it rarely: every commit of changed binary data stays in the repository
history. Also check the PeMS terms of use before republishing processed data, and see *Credits* for the map tiles.

## Where the data comes from, and how it is built
Source: Caltrans Performance Measurement System, <https://pems.dot.ca.gov> (free account). The project does not use
all days: a stratified sample of 180 days was downloaded (about 5.4 GB, 18 days per 12 months: every weekday three
times a year, weekends once or twice, all seasons, holidays and the days around them excluded). See
[SAMPLING_PLAN.md](SAMPLING_PLAN.md) for the statistics behind this and how noisy single-point numbers are.

```
tools/plan_sample.py     writes sampling_plan.csv (which days to download, in three nested tiers; "xlean" = the 180)
tools/calendar_rules.py  holiday / atypical-day rules shared by the plan and the processor
tools/pems_to_app.py     raw PeMS files -> data/  (and data/est/ with PeMS-estimated values included)
tools/writer.py          writes the compressed data files (called by the above)
tools/receive_server.py  optional: localhost receiver used to save browser-fetched downloads into the project folder
tools/make_demo_data.py  synthetic demo data (writes to ./data - it overwrites real data!)
```

Rebuild from the raw files (put the downloaded `d04_text_station_5min_*.txt.gz` files and a
`d04_text_meta_*.txt` station metadata file in the project folder):

```bash
python tools/pems_to_app.py . --slot-minutes 5      # needs Python 3 and numpy; ~15 min, ~6 GB RAM
python tools/plan_sample.py status                  # which planned files are downloaded / missing
```

Per-file summaries are cached in `pems_cache/`, so later runs only process new files and the raw files can be deleted
with `--delete-raw`.

### Data layout (`data/`, `data/est/`)
| File | Contents |
|---|---|
| `meta.json` | resolution, year range, where each freeway direction sits in the detector list |
| `stations.json` | detector id, freeway, direction, location, postmile, free-flow speed (shared by `est/`) |
| `map_<year>.bin.gz` | yearly average speed, `[day of week][5-minute slot][detector]`, one byte each (255 = no data) |
| `hist/<freeway><dir>.bin.gz` | month-by-month history of every detector on that freeway direction, 15-minute resolution |

## Limitations worth knowing
- Speeds come mostly from single-loop detectors that estimate speed; they separate slow from free-flowing well but are
  not reliable above about 65 mph.
- Many detectors have long outages (most of the real gaps in the data); the PeMS-estimates switch fills them with
  PeMS's own guesses.
- With the 180-day sample, a single detector on a single weekday in a single year averages only three days. Use year
  ranges, Tue–Thu / Mon–Fri, and the smoothed trends for reliable readings.
- Detectors that are no longer in the current PeMS metadata cannot be placed on the map and are skipped.

## Credits
Traffic data: Caltrans PeMS. Map data © OpenStreetMap contributors (tiles from tile.openstreetmap.org — fine for
personal use; for a popular public site use a tile provider with an API key instead, see the OSM tile usage policy).
Libraries: Leaflet, Chart.js, chartjs-plugin-zoom, Hammer.js.
