# Buffett/Munger Moat Lane Scanner

Autonomous daily scoring system for S&P 500 + Russell 1000 (~1,013 stocks) using Warren Buffett and Charlie Munger's investment framework.

**Live dashboard:** https://buffet-scanner.vercel.app

## How it works

Every morning at 7am Helsinki time a GitHub Action:
1. Fetches live S&P 500 constituents (Wikipedia) and Russell 1000 (iShares IWB)
2. Scores every stock across 4 pillars using real yfinance market data
3. Runs Munger inversion analysis on each name
4. Asks Gemini to write a leaderboard narrative
5. Commits results and deploys to Vercel automatically

## Scoring model

Each stock is scored 0–10 across four pillars:

| Pillar | Weight | What it measures |
|--------|--------|-----------------|
| Quality | 30% | ROIC, earnings predictability, FCF conversion, gross margins |
| Management | 25% | Insider ownership (dollar-adjusted for mega-caps), recent transactions |
| Moat | 25% | Gross/operating margins vs peers, revenue growth consistency |
| Valuation Fit | 20% | Forward P/E, 52-week range position, owner earnings yield |

**Verdicts:** Own Forever (≥8.0) · Watchlist (6.0–7.9) · Pass (4.0–5.9) · Avoid (<4.0)

**Munger Inversion:** Each stock is stress-tested against 3 killers — technology disruption, debt spiral, and governance failure. Names with 2+ material killers are flagged regardless of score.

## Data integrity

All scores are derived from live yfinance data (Yahoo Finance). Known limitations:
- `heldPercentInsiders` can misclassify large institutional holders (e.g. Berkshire) as insiders — the scorer detects and corrects this automatically
- `earningsGrowth` is TTM quarterly, capped at 25% for margin of safety calculations
- Inversion probabilities (25%/30%) are heuristic thresholds, not empirically calibrated

## Running locally

```bash
pip install -r requirements.txt

# Scan full universe
python3 scanner.py

# Scan specific universe
python3 scanner.py --universe sp500
python3 scanner.py --universe russell
python3 scanner.py --universe sp100

# Score a single stock
python3 models/moat_lane.py MSFT

# Launch dashboard
python3 serve.py
```

## Stack

- **Scoring:** Python + yfinance — no LLM involved in stock analysis
- **Narrative:** Gemini Flash (leaderboard.md only)
- **Dashboard:** React (CDN, no build step) + vanilla CSS
- **Hosting:** Vercel (auto-deploys on every GitHub push)
- **Scheduling:** GitHub Actions cron (daily 04:00 UTC)
