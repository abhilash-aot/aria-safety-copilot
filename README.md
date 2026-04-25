# 🛡️ Safety Copilot

> An AI-assisted operations dashboard for volunteer-run meal-delivery services —
> turns a messy schedule into a **safe-by-construction** delivery plan, with a
> character-driven UI a coordinator can open on their phone at 7 AM.

Built for the **BuildersVault Social Services Hackathon 2026 — Track 2: Food Security Delivery**.

![Login gate](docs/screenshots/00_login.png)

---

## What it does

Five distinct personas, one app:

- **🏠 Volunteer Lead** — Tuesday-morning operations: anomaly review, one-click fixes, the whole route plan.
- **🚚 Driver** — in-truck stop clipboard for a single driver.
- **📊 Coordinator** — weekly KPIs, driver burnout watchlist, fleet health.
- **🔐 Auditor** — proof-of-correctness pages with file:line citations.
- **🎭 Demo mode** — every page visible (for stakeholders, judges, walkthroughs).

The **optimizer is safe-by-construction**: it pre-filters every hard constraint
(severe allergens, cold chain, wheelchair lift, driver hours) *before* assembling
routes, so the output plan is guaranteed to contain **0 CRITICAL / 0 HIGH** safety
violations across every measured day.

---

## Quick start

```bash
# 1. install dependencies (once)
python -m pip install -r requirements.txt

# 2. generate the synthetic Track 2 dataset (once, ~30s)
python tracks/food-security-delivery/generator/generate.py

# 3. run the Streamlit app
python -m streamlit run app/copilot.py
# opens http://localhost:8501
```

Pick a role on the login gate and explore. **Demo mode** unlocks every page.

**Other entry points:**
```bash
python demo.py                                    # CLI preview for 2026-04-14
python -m pytest tests/ -q                        # 31 pass / 1 skip
python eval/scorecard.py --out eval/              # regenerate eval/SCORECARD.md
```

**Direct-link any role** (skips the picker):
```
http://localhost:8501/?role=volunteer
http://localhost:8501/?role=driver
http://localhost:8501/?role=coordinator
http://localhost:8501/?role=auditor
http://localhost:8501/?role=demo
```

---

## Screenshots

### Login gate
Five roles. Each scopes the sidebar nav and routes to the relevant primary page.

![Login gate](docs/screenshots/00_login.png)

### Hero + Risk Snapshot + streaming briefing
ARIA the animated character reacts to severity. **Risk Snapshot** shows how much of the raw schedule's risk has been cleared (climbs as fixes are applied — no more alarming "0 / 100" misreads). Briefing streams in like Claude with operator IDs auto-highlighted as code pills.

![Hero & briefing](docs/screenshots/02_hero_briefing.png)

### "The Plan" — before/after panel + flowing route map
Dark hero panel: baseline 5,106 drive-min vs ARIA's 103. Map shows status-coloured stops, AntPath flowing polylines, pulsing depot halos, floating legend.

![The Plan](docs/screenshots/03_the_plan.png)

### Anomalies — review and one-click fix
Severity-bordered cards (critical = red pulse, high = orange pulse), staggered slide-in. Each card has an **Apply fix** button that mutates an in-memory overlay; the plan above refreshes automatically.

![Anomalies](docs/screenshots/04_anomalies.png)

### Coordinator — weekly operations + fleet health
Two tabs: **Weekly Operations** (KPIs, burnout watchlist, fairness gini, scorecard summary) and **Fleet Health** (driver utilization gauges, vehicle capability cards). Replaces the previous Operator + Fleet pages.

![Coordinator](docs/screenshots/05_coordinator.png)

### Driver — stop clipboard + helpful empty state
Per-driver header card, vehicle/depot/shift metrics. When no route is assigned for the selected date, a helpful nudge: who *is* driving today, and which dates this driver covers — two clicks to un-stick.

![Driver](docs/screenshots/06_driver.png)

### Surplus Match
Connect a restaurant's surplus food to eligible neighbours. Three demo presets (dairy / peanut / wheat allergens), folium mini-map, automatic safety blocking, "saved from landfill" impact chip.

![Surplus Match](docs/screenshots/07_surplus.png)

### Scorecard
Per-detector P/R/F1 with animated progress bars. Recall = 1.00 across every seeded case. Optimizer delta vs baseline. ARIA vs baseline constraint audit.

![Scorecard](docs/screenshots/08_scorecard.png)

### Safety Audit
8 hard constraints, each with the file:line where it's **detected** and where it's **enforced** — the safety claim is verifiable code, not marketing.

![Safety Audit](docs/screenshots/09_safety_audit.png)

---

## Architecture

```
┌────────────────────────────────────────────────────────────┐
│   Streamlit UI  ·  app/copilot.py + app/pages/*.py         │
│                                                            │
│   _role.py     _character.py   _calendar.py   _layout.py   │
│   _sections.py _fleet_view.py  _data.py                    │
└──────────┬────────────────┬──────────────────┬─────────────┘
           │                │                  │
           ▼                ▼                  ▼
    ┌───────────┐    ┌──────────────┐   ┌──────────────┐
    │src/safety │    │src/optimizer │   │src/surplus   │
    │ detectors │    │ constrained  │   │   matcher    │
    │ fix_engine│    │    greedy    │   │              │
    │ score     │    │   baseline   │   │              │
    │ models    │    │     vrp      │   │              │
    └─────┬─────┘    └──────┬───────┘   └──────┬───────┘
          │                 │                  │
          └────────┬────────┴──────────────────┘
                   ▼
          ┌──────────────────┐
          │ shared/src       │  ← load_track2()
          │ loaders.py       │
          └──────────┬───────┘
                     ▼
          ┌──────────────────┐
          │ Parquet files    │  ← no database, no cloud
          └──────────────────┘
```

**Key principle**: `src/` is pure Python over pandas DataFrames. No Streamlit imports. The same code powers the UI, the eval harness, and the test suite.

---

## Role-based access

| Role | Lands on | Sidebar shows | Primary use |
|---|---|---|---|
| 🏠 **Volunteer Lead** | ARIA Home | Home + Surplus | Tuesday morning dispatch — anomalies, fixes, plan |
| 🚚 **Driver** | Driver page | Driver | In-truck stop clipboard for a single driver |
| 📊 **Coordinator** | ARIA Home | Home + Coordinator + Surplus | Weekly KPIs, burnout, fleet, donations |
| 🔐 **Auditor** | Scorecard | Scorecard + Safety Audit | Verify safety claims (file:line citations) |
| 🎭 **Demo** | ARIA Home | Everything | Walkthrough / stakeholder review |

The role gate is enforced both in `app/copilot.py` (login + auto-redirect) and in
each sub-page via `app/_role.py::enforce_role(allowed)`. Sidebar nav links are
hidden via injected CSS targeting `[data-testid="stSidebarNavLink"][href$="/X"]`.

---

## Features in depth

### 🛡️ 8 safety detectors (`src/safety/detectors.py`)

| Rule | Severity | Catches |
|---|---|---|
| `check_severe_allergen` | 🔴 CRITICAL | Line items with an allergen the client is severe/anaphylactic about |
| `check_cold_chain` | 🔴 CRITICAL | Cold-chain requests on a non-refrigerated vehicle |
| `check_wheelchair_lift` | 🟠 HIGH | Wheelchair client assigned to any vehicle except VEH-06 |
| `check_two_person_solo` | 🟠 HIGH | Two-person client on a single-driver route (respects `partner_driver_id`) |
| `check_post_closure_delivery` | 🟡 MEDIUM | Delivery scheduled after the client's file closure date |
| `check_driver_pet_allergy` | 🟡 MEDIUM | Pet-allergic driver at a client with a dog on premises |
| `check_interpreter_language` | 🟡 MEDIUM | Interpreter needed but driver lacks the language |
| `check_driver_hours_distance` | ⚪ LOW | Weekly hours/distance cap nearing |

**Measured recall = 1.00** on every seeded ground-truth case (3/3 allergen, 4/4 post-closure, 7/7 two-person solo).

### 🚚 Safe-by-construction optimizer (`src/optimizer/constrained_greedy.py`)

Nearest-neighbour greedy VRP with hard-constraint pre-filtering:
1. Drop closed/deceased clients
2. Drop allergen-blocked requests
3. Per-request eligibility matrix (vehicle + driver skills + language + pet allergy)
4. Per-route caps (`max_stops`, `max_distance_km`, `max_hours`, weekly ISO-week sum)

Output: `{routes, dropped_requests, total_drive_minutes, baseline_drive_minutes, delta_pct, projected_on_time_rate, violations=[]}`.

Measured across 11 sampled service dates: **0 CRITICAL + 0 HIGH** violations vs baseline's mean **0.09 CRITICAL + 15.82 HIGH** per day.

Bonus: `src/optimizer/vrp.py` ships an **OR-Tools VRP** alternate (`PATH_CHEAPEST_ARC` + `GUIDED_LOCAL_SEARCH`, 10s time-limit) with the same interface.

### 📊 Risk Snapshot (`src/safety/score.py`)

Severity-weighted (CRITICAL=10, HIGH=5, MEDIUM=2, LOW=1) risk score that climbs as fixes are applied:
- `raw == 0` → "✅ Schedule clean"
- `raw > 0, current == 0` → "✅ All N risk pts cleared"
- `cleared > 0` → "🔧 X of Y risk pts cleared · keep going"
- no fixes yet → "⚠️ N risk pts in today's schedule · apply fixes below"

Bar fills with "% of raw risk cleared" — starts at 0% (truthful), climbs visibly as fixes land.

### 🔧 Fix engine with session overlay (`src/safety/fix_engine.py`)

Seven fix proposers — `item_substitute`, `vehicle_swap`, `stop_cancel`, `driver_swap`, `route_pair`, `route_redistribute`, plus an item-alternate ranker. Each produces a `{table, where, set}` patch applied to an **in-memory overlay** — source parquet is never written. Clicking Reset clears all applied fixes.

### 🍱 Surplus Match (`src/surplus/matcher.py` + page)

When a restaurant or kitchen has surplus food to donate:
1. Filters to `enrolment_status == "active"` clients (~378 of 500)
2. Canonicalises allergen aliases (`milk → dairy`, `gluten → wheat`, `nut → tree_nut`)
3. **Hard-stops on severe / anaphylactic** client allergies
4. Ranks survivors by `food_security_level` (severe first), then proximity
5. Also returns the top 5 nearby **excluded** clients so the UI can show the safety story

Three demo scenario presets, folium mini-map with green / red pins, waste-saved impact chip.

### 📅 Severity calendar

Sidebar monthly grid; every day coloured by its worst violation severity. Click a cell → URL query param → the whole UI updates for that date. Cached for the session.

### 🎭 ARIA — the character

Animated SVG shield with 4 severity-reactive states:

| State | Trigger | Visual |
|---|---|---|
| `happy` | 0 violations | 🟢 green, gentle float, smile |
| `ok` | low/medium only | 🔵 teal, steady |
| `warning` | any HIGH | 🟠 amber, faster pulse, wide eyes |
| `critical` | any CRITICAL | 🔴 red, shake, alarmed mouth |

The sidebar brand chip and severity calendar all react to the same state.

---

## The dataset

| Table | Rows | What |
|---|---|---|
| `depots` | 2 | Distribution hubs with lat/lng |
| `vehicles` | 8 | 5 refrigerated, 1 with wheelchair lift (VEH-06) |
| `drivers` | 8 | Language skills, pet allergy, max hours, wheelchair certified |
| `clients` | 500 | Allergy severity per type, food security level, mobility, consent |
| `requests` | 10,000 | cold_chain, required_driver_skills, scheduled_date |
| `items` | 150 | allergen_flags, dietary_tags, cold_chain_required |
| `request_items` | ~24,000 | Line items: request × item × quantity |
| `routes` | 300 | service_date, driver, vehicle, planned minutes |
| `stops` | ~3,500 | status ∈ {completed, skipped, no_answer, cancelled, rerouted} |

The data is **synthetic** (generated by `tracks/food-security-delivery/generator/generate.py`)
but deliberately messy — phone formats, date formats, nulls, 9 seeded red-flag patterns with ground truth.

---

## Tech stack

- **Runtime**: Python 3.10+
- **UI**: Streamlit · streamlit-folium · streamlit-extras
- **Data**: pandas · pyarrow · parquet on disk (no DB)
- **Maps**: folium + CartoDB Positron tiles (free, no token)
- **Optimizer**: custom constrained greedy; OR-Tools VRP alternate
- **Tests**: pytest
- **Dev**: playwright (reproducible PR/README screenshots)

**No external services at runtime** — no LLM API, no cloud, no geocoder. Brief is templated. Map tile CDN is the only network dependency, and ARIA's SVG character renders offline.

---

## Repo structure

```
.
├── app/                          Streamlit UI
│   ├── copilot.py                landing + login gate
│   ├── _role.py                  enforce_role + role chip + nav filter
│   ├── _character.py             ARIA animated SVG
│   ├── _calendar.py              severity calendar in sidebar
│   ├── _sections.py              brief / anomalies / map renderers
│   ├── _layout.py                global CSS + animations
│   ├── _data.py                  shared cached loaders
│   ├── _fleet_view.py            fleet-health renderer (used by Coordinator)
│   └── pages/                    5 sub-pages
│       ├── 2_🚚_Driver.py
│       ├── 2_📈_Scorecard.py
│       ├── 3_📊_Coordinator.py   tabs: Weekly Operations + Fleet Health
│       ├── 3_🔐_Safety_Audit.py
│       └── 4_🍱_Surplus.py
├── src/
│   ├── safety/                   detectors + models + fix_engine + score
│   ├── optimizer/                constrained_greedy + vrp + baseline
│   ├── brief/                    templated morning brief
│   ├── surplus/                  surplus-food matcher
│   └── io/                       golden join helper
├── shared/                       kit-provided loaders + validators
├── tracks/food-security-delivery/
│   ├── generator/                synthetic data generator
│   ├── data/raw/                 parquet files (gitignored; regenerate via generator)
│   └── data/sample/              sample CSVs committed for preview
├── eval/
│   ├── scorecard.py              detector accuracy + optimizer delta CLI
│   ├── scorecard.json            machine-readable numbers
│   └── SCORECARD.md              human-readable table
├── tests/                        pytest suite
├── scripts/
│   └── capture_screenshots.py    Playwright-based README screenshot regen
├── docs/
│   ├── overview.md               starter-kit overview
│   └── screenshots/              README imagery
├── demo.py                       CLI preview of the pipeline
├── requirements.txt
├── LICENSE                       MIT
└── DATA_LICENSE.md               CC BY 4.0 (synthetic data)
```

---

## Development

### Regenerate screenshots

```bash
# terminal 1 — run the app headlessly on a dedicated port
python -m streamlit run app/copilot.py --server.port 8530 --server.headless true

# terminal 2 — capture every page (uses ?role=demo backdoor for clean session)
python scripts/capture_screenshots.py --port 8530 --out docs/screenshots
```

### Regenerate the scorecard

```bash
python eval/scorecard.py --out eval/
# writes eval/scorecard.json + eval/SCORECARD.md
```

### Run the tests

```bash
python -m pytest tests/ -q
# 31 pass, 1 skip (~90s — OR-Tools test is the slow one)
```

---

## Safety & data posture

- **No PHI / no real client data.** Everything is synthetic. See `DATA_LICENSE.md`.
- **Allergen matching** is a strict hard-stop on severity ∈ `{severe, anaphylactic}`. Lesser severities are not used for automated blocking.
- **Session overlay fixes** are ephemeral — the raw parquet is never modified.
- **Role gating** is UI-level (sidebar filter + `enforce_role` redirect) — for a real production deploy, wrap in proper auth.
- **`.claude/`, `.env`, `.streamlit/secrets.toml`** are gitignored.

---

## License

- Code: [MIT](LICENSE)
- Synthetic data: [CC BY 4.0](DATA_LICENSE.md)

Built on the [BuildersVault Social Services Hackathon starter kit](https://luma.com/uvqu2y5o).
