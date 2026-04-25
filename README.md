# 🛡️ ARIA — Safety Copilot

> Character-driven operations dashboard for volunteer-run meal-delivery services —
> turns a messy schedule into a **safe-by-construction** delivery plan.

**🚀 Live demo — [aria-safety-copilot.streamlit.app](https://aria-safety-copilot.streamlit.app/)** · pick **🎭 Demo** on the login gate to unlock every page.

Built for the [BuildersVault Social Services Hackathon 2026 — Track 2: Food Security Delivery](https://luma.com/uvqu2y5o).

![Login gate](docs/screenshots/00_login.png)

---

## What it does

Five roles share one app:

| Role | Purpose |
|---|---|
| 🏠 **Volunteer Lead** | Tuesday-morning dispatch — anomalies, fixes, route plan |
| 🚚 **Driver** | In-truck stop clipboard for one driver |
| 📊 **Coordinator** | Weekly KPIs, burnout watchlist, fleet health |
| 🔐 **Auditor** | Proof-of-correctness pages with `file:line` citations |
| 🎭 **Demo** | Every page visible |

The optimizer is **safe-by-construction**: it pre-filters every hard constraint (severe allergens, cold chain, wheelchair lift, driver hours) *before* assembling routes — guaranteeing **0 CRITICAL / 0 HIGH** safety violations in the output.

Measured detector recall = **1.00** across every seeded case. See [`eval/SCORECARD.md`](eval/SCORECARD.md).

---

## Quick start

```bash
pip install -r requirements.txt
python -m streamlit run app/copilot.py
# → http://localhost:8501
```

The synthetic dataset is committed under `tracks/food-security-delivery/data/raw/` so the app runs out of the box. To regenerate it, run `python tracks/food-security-delivery/generator/generate.py` (~30s).

**Other entry points:**

```bash
python demo.py                          # CLI preview for 2026-04-14
python -m pytest tests/ -q              # 31 pass / 1 skip
python eval/scorecard.py --out eval/    # regenerate eval/SCORECARD.md
```

**Direct-link any role** (skips the picker):

```
http://localhost:8501/?role=volunteer|driver|coordinator|auditor|demo
```

---

## Architecture

```
Streamlit UI (app/)  →  pure-Python core (src/safety, src/optimizer, src/surplus)
                     →  parquet on disk (no DB, no cloud, no LLM at runtime)
```

The `src/` layer has no Streamlit imports, so the same code powers the UI, the eval harness (`eval/scorecard.py`), and the pytest suite (`tests/`).

---

## Deeper reading

- **[docs/features.md](docs/features.md)** — 8 safety detectors, optimizer internals, risk scoring, fix engine, surplus matcher, ARIA character, dataset tables, repo layout
- **[docs/screenshots.md](docs/screenshots.md)** — walkthrough of every page
- **[eval/SCORECARD.md](eval/SCORECARD.md)** — measured detector accuracy + optimizer delta

---

## Safety & data posture

- **No PHI / no real client data.** Everything is synthetic — see [DATA_LICENSE.md](DATA_LICENSE.md).
- **Allergen matching** is a strict hard-stop on severity ∈ `{severe, anaphylactic}`.
- **Session overlay fixes** are ephemeral — the raw parquet is never modified.
- **Role gating** is UI-level — wrap in proper auth for production.
- **`.env`, `.streamlit/secrets.toml`** are gitignored.

---

## Tech stack

Python 3.10+ · Streamlit · pandas · folium · OR-Tools (optional alternate optimizer) · pytest · Playwright (screenshot regen).

No external services at runtime — no LLM API, no cloud, no geocoder. Map tile CDN is the only network dependency.

---

## License

- Code: [MIT](LICENSE)
- Synthetic data: [CC BY 4.0](DATA_LICENSE.md)
