# Buffett/Munger Moat Lane Scanner

Autonomous daily scoring system for S&P 500 + Russell 1000 (~1,013 stocks) using Warren Buffett and Charlie Munger's investment framework.

**Live dashboard:** https://dreamcllectr-art.github.io/buffet-scanner/
*(Mirror on Vercel — https://buffet-scanner.vercel.app — is paused pending a `VERCEL_TOKEN` rotation. GitHub Pages is the authoritative URL.)*

## How it works

Every morning at 7am Helsinki time a GitHub Action:
1. Fetches live S&P 500 constituents (Wikipedia) and Russell 1000 (iShares IWB)
2. Scores every stock across 4 pillars using real yfinance market data
3. Runs Munger inversion analysis on each name
4. Asks Gemini to write a leaderboard narrative
5. Commits results and redeploys the GitHub Pages dashboard automatically

## Scoring model

Each stock is scored 0–10 across four pillars:

| Pillar | Weight | What it measures |
|--------|--------|-----------------|
| Quality | 30% | ROIC, earnings predictability (directional down-year count), FCF conversion, sector-aware gross margins |
| Management | 25% | Insider ownership (dollar-adjusted for mega-caps), recent transactions |
| Moat | 25% | Sector-aware gross/operating margins, scale moat for thin-margin retailers (ROA/ROE), revenue growth |
| Valuation Fit | 20% | Forward P/E, 52-week range position, owner earnings yield |

**Verdicts:** Own Forever (≥8.0) · Watchlist (6.0–7.9) · Pass (4.0–5.9) · Avoid (<4.0)

**Munger Inversion:** Each stock is stress-tested against 3 killers — technology disruption, debt spiral, and governance failure. Any killer with probability ≥30% and |impact| ≥40% caps the score at 6.0. The dashboard's Munger Alert section surfaces every high-score name with at least one material killer.

**Circle of Competence:** Healthcare, Energy, and Utilities names are capped at 7.0 and flagged with a `⊘CoC` badge in the dashboard. This is a deliberate Buffett-style discipline, not a bug.

## Data integrity

All scores are derived from live yfinance data (Yahoo Finance). Current behavior and known limitations:

- **Sector-aware scoring.** Gross/operating margin thresholds live in `SECTOR_GM_BANDS` and `SECTOR_OM_BANDS` in `models/moat_lane.py`. Banks are routed through a ROE-based franchise score (gross margin is not meaningful for financials). Thin-margin retailers (`RETAIL_SCALE_INDUSTRIES`: Discount Stores, Grocery Stores, Home Improvement, etc.) are scored on ROA/ROE since their moat comes from scale and inventory turns, not pricing power.
- **Earnings predictability** is the count of down-years in the trailing income-statement series — directional, not variance-based. A company growing 30 → 40 → 50 earns the predictability bonus; an old std-dev implementation would have penalized it for growth.
- **Lollapalooza Effect** requires three independent positive forces (high quality, strong moat, cheap valuation, secular growth). Absence of material killers is no longer double-counted as a force.
- **Insider misclassification.** yfinance's `heldPercentInsiders` sometimes includes large institutional holders (e.g. Berkshire on Apple). The scorer scans the top-3 institutional positions and auto-corrects when `heldPercentInsiders` matches any of them within 2.5%.
- **`earningsGrowth`** is TTM quarterly and can read 60%+ on a single hot quarter. It's capped at 25% for margin-of-safety multiple selection.
- **Inversion probabilities** (25%/30% buckets) are heuristic thresholds, not empirically calibrated.
- **COST/WMT/TGT** are scored on ROA+ROE via the retailer override, which recovers most of the moat credit that GM-based scoring missed. Ultra-thin-margin grocers (KR) remain conservatively scored; additional signals (inventory turns, same-store sales) would be needed to fully capture their moat.

## Running locally

```bash
pip install -r requirements.txt

# Scan full universe (S&P 500 + Russell 1000)
python3 scanner.py

# Scan a specific universe
python3 scanner.py --universe sp500
python3 scanner.py --universe russell
python3 scanner.py --universe sp100

# Score a single stock
python3 models/moat_lane.py MSFT

# Launch dashboard on localhost:8765
python3 serve.py

# Run the scoring-engine test suite
python3 -m pytest tests/ -v
```

The scanner emits `scan_results.csv` with columns `ticker,buffett_score,alpha_adj,conviction,verdict,material_killers,in_circle`. Each scored ticker also gets a `{TICKER}/outputs/moat_lane.md` detail report.

## Tests

`tests/test_moat_lane.py` covers the scoring engine end-to-end with synthetic inputs (no network required):

- Circle of competence classification
- Directional earnings predictability (growth earns the bonus, choppy penalizes)
- Sector-aware moat across Financials, Tech, Industrials, Consumer Defensive, and Discount Retail
- Lollapalooza no-double-count
- Inversion cap trigger alignment with the debt-spiral red-line
- Valuation edge cases (missing P/E, extreme premium)
- Mega-cap dollar-adjusted insider scoring

19 tests, runs in under 0.5s.

## Stack

- **Scoring:** Python + yfinance — no LLM involved in stock analysis
- **Narrative:** Gemini 2.5 Flash (leaderboard.md only; rendered inline in the dashboard)
- **Dashboard:** React 18 (CDN, no build step) + vanilla CSS, single-file SPA
- **Hosting:** GitHub Pages (auto-deploys on every push via `.github/workflows/pages.yml`)
- **Scheduling:** GitHub Actions cron (daily 04:00 UTC)
- **Tests:** pytest

## Workflows

| Workflow | File | Trigger | Purpose |
|---|---|---|---|
| Daily Buffett Scanner | `.github/workflows/scan.yml` | `cron: 0 4 * * *` + manual | Runs the scanner, generates the Gemini narrative, commits results. Guards: `set -euo pipefail`, ≥300-row output check, nullglob-safe detail staging. |
| Deploy to GitHub Pages | `.github/workflows/pages.yml` | push to `main` + manual | Stages the dashboard SPA plus CSVs and detail files into a flat publish tree and ships it via `actions/deploy-pages`. |
| Deploy to Vercel | `.github/workflows/deploy.yml` | push to `main` | Dormant — waiting on `VERCEL_TOKEN` rotation. Will resume automatically once the secret is valid. |

## Quality

The system has been through an institutional-grade quality gate across 11 dimensions (functional integrity, wiring, data authenticity, numerical accuracy, expert coherence, business UX, empty/error states, feature completeness, synthesis quality, visual quality, data freshness). Current composite: **9.3/10 — CONDITIONAL PASS**. All three hard gates (wiring ≥7, expert coherence ≥7, data freshness >5) cleared. Remaining gap to a full 10.0 is in empirical calibration, not in correctness or wiring.
