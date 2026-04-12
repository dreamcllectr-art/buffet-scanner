# I Built a Buffett/Munger Analyst That Scores the S&P 500 + Russell 1000 Before I Wake Up. It Runs on a Cron Job.

A friend asked me last week whether JPM was a buy. I ran my scorer on it. The verdict came back "Pass, gross margin too low." JPM. Too low gross margin.

Gross margin is meaningless for a bank. My scorer had been applying software-company thresholds to every financial in the index and I hadn't noticed.

I spent the next two days rebuilding the thing end to end.

**Before**
– 4 hours per name, one stock at a time
– Bloomberg → Excel → EDGAR → gut feel
– $24k/year Bloomberg seat
– Absolute thresholds that silently penalized every bank, retailer, and insurer in my universe

**After**
– 929 names across the S&P 500 + Russell 1000, scored every morning in under seven minutes
– Live yfinance data, committed to git, served from a free CDN
– $0 marginal cost on GitHub Actions, GitHub Pages, and free APIs
– Sector-aware 4-pillar scoring, Munger inversion, a cyclicality penalty, and 22 unit tests catching the class of bug I had been shipping to my own research

Here's how I use it.

![The Oracle's Ledger, top of the live leaderboard, 929 names scored against the S&P 500 + Russell 1000 universe](images/01-hero.png)

*Every row on that leaderboard is live at `buffet-scanner.vercel.app`. Click any ticker and the detail panel expands. Behind the paywall below is the mechanism that produced those scores, the code to run your own copy, and the result I'm still uncomfortable with.*

---

## A Scanner Built to Think Like Buffett, Not Like a Screener

I type one command:

> _python3 scanner.py --universe all --top 25 --workers 2_

Seven minutes later I'm looking at the dashboard above. Eighteen names in Own Forever territory: NVDA leads at 8.9, then MSFT 8.8, GOOGL 8.6, NEU 8.5, APP 8.4, ROL 8.4, MEDP 8.4, SEIC 8.4, AM 8.4, CTAS 8.3, FTNT 8.3, LOPE 8.3. Half of those names I'd never think to pull up manually.

When I click a row, the detail panel expands inline:

![NVDA detail panel: four pillars, three inversion killers, five mental models, Lollapalooza check](images/02-detail-panel.png)

Four pillar scores. Three inversion killers with probability and fair-value impact estimates. Five mental models. A Lollapalooza check. NVDA scored Quality 8.5, Management 9.0, Moat 9.5, Valuation Fit 8.5, with four forces aligning on Lollapalooza. Then look at the Quality rationale: *"5y price drawdown: 66% (severe cyclicality)"*. The scorer docked NVDA 1.5 Quality points for that one line, and it's the single most important thing the system caught this week.

> **The scorer puts NVDA at the top. That's the wrong answer, and the one-line fix I added to catch it taught me more about Buffett than the other 800 lines of code combined.**

No LLM picks any stock. Scoring is deterministic Python on live yfinance data, reproducible across runs, auditable line by line. Gemini only writes the daily narrative the dashboard displays beneath the table.

For the research I used to do in a spreadsheet, it replaces most of what I used Bloomberg for.

---

## Why I Built This

A few weeks ago I was doing value research the usual way:

*   Pull financials from Yahoo
*   Eyeball margins, skim the 10-K
*   Run a quick DCF in a spreadsheet
*   Check insider activity
*   Write a one-page note nobody reads again

I timed it. One name, done properly, took four hours. And I was still shipping the JPM bug: an absolute gross-margin threshold that was mechanically punishing every financial in the index.

I started wondering what would happen if the whole workflow (universe selection, scoring, inversion, narrative, publish) ran end to end overnight.

After a hard refactor, 880 lines of scoring code, 22 unit tests, and an audit I ran against my own build, it was clear the automated version was more rigorous than anything I'd been doing manually. Mostly because it doesn't skip steps when I'm tired, and it doesn't forget that banks don't have gross margins.

---

## The Economics

A junior buy-side value analyst costs $120k to $180k all-in. A senior one runs $200k to $300k. In return you get:

*   Coverage of 15 to 25 names
*   Models refreshed quarterly
*   Finite attention and real blind spots
*   A Bloomberg terminal nobody will let you cancel

This runs on a laptop and a GitHub Actions runner. Infrastructure: $0. Data: $0.

It scores the same 929 names from the S&P 500 + Russell 1000 every morning, with the same discipline on every ticker. The ~80 tickers that don't make it through are yfinance data gaps and get listed as errors in the run log.

Here's what's behind the cut:

*   **The full code in a Google Drive folder.** Scoring engine, scanner, dashboard, 22 unit tests, scheduled workflow. Clone it, tune it, point it at your own universe.
*   **Why NVDA at 8.9 is still the wrong answer, and the cyclicality penalty that caught it.** The exact 5y price drawdown math, the threshold that docks a name 1.5 Quality points, and why I'd still refuse to buy NVDA on the scorer's green light.
*   **The one-line change that moved JPM from Pass to 7.3 Watchlist**, unblocked every bank in the universe, uncapped Healthcare and Energy, and surfaced COST after the retailer scale-moat override fired.
*   **The Munger inversion cap math with the off-by-one I almost shipped.** Probability and impact thresholds were set just above where any real killer could fire.
*   **The full 4-pillar rubric**, including the sector-band dictionary that fixes the bank/retailer problem in one file.

*Know anyone who still pays for a Bloomberg terminal? Forward this.*

<!-- SUBSTACK_PAYWALL -->

---

## What Today's Scan Actually Found

Eighteen names cleared Own Forever today. Starting with the uncomfortable one:

*   **NVDA, 8.9.** Quality 8.5, Management 9.0, Moat 9.5, Valuation Fit 8.5. Every underlying metric is dominant, and Lollapalooza lit up on four forces: high quality, strong moat, attractive valuation, secular growth. Then the Quality rationale shows *"5y price drawdown: 66% (severe cyclicality)."* I added that penalty after realizing Buffett's actual bar isn't "do I understand semis," it's "can I predict earnings through the next downturn." NVDA has lost 60% of its market cap twice in the last decade. The scorer docks it 1.5 Quality points for it, which drops the composite from what would have been 9.3 down to 8.9. It's still at the top because the raw fundamentals are that strong, but I wouldn't buy it. Chips are structurally cyclical, the hyperscalers are openly trying to commoditize CUDA with custom silicon (Google TPU, Amazon Trainium, Microsoft Maia), and "predictable through the next downturn" is a harder test than any one year's ROIC can pass. The scorer does the quantitative work. I still have to do the qualitative work myself.
*   **MSFT, 8.8.** Zero cyclicality penalty, monotonic earnings, same top-5 spot every scan for the last three weeks. Material killer count of 2. Tech disruption is always flagged as material for big tech, which is honest.
*   **GOOGL, 8.6.** Same profile. Moderate cyclicality ding for the 2022 ad-revenue drawdown, otherwise clean.
*   **ROL (Rollins), 8.4.** Pest control. Zero material killers. 50% operating margins. Buffett would call this a toll bridge.
*   **CTAS (Cintas), 8.3.** Uniform rental. Boring industrial. Zero material killers. Sector-aware moat scoring catches it where a gross-margin screener wouldn't.
*   **SEIC, MEDP, LOPE, NEU, AM.** All 8.4 or 8.3. Financial services, medical research, for-profit education, specialty chemicals, natural gas midstream. None of these would clear an absolute-threshold screener built in 2019. All of them clear the sector-aware rubric in 2026.

The more interesting story is the names that moved **up** after the sector-aware rewrite. JPM went from "below the cut" to 7.3 / Watchlist the instant the scorer stopped treating financials like software companies. BAC landed at 6.1. COST climbed from 5.2 to 6.4 once the retailer scale-moat override fired. LLY moved to 7.7 after I pulled the circle-of-competence cap off Healthcare entirely.

Every one of those was a bug my old scorer was shipping into my own research, and I hadn't noticed any of them.

---

## The 4 Pillars

Every stock is scored 0 to 10 across four pillars, weighted the way Buffett has actually written about them:

| Pillar | Weight | What it really measures |
|---|---|---|
| Quality | 30% | ROIC, earnings predictability as **count of down-years** (not std-dev, which penalizes growth), FCF conversion, sector-aware gross margins, 5y price drawdown for cyclicality |
| Management | 25% | Insider ownership in **dollars**, not percent. 0.5% of a $3T company is $15B of skin. |
| Moat | 25% | Sector-aware margins, plus a scale-moat override for thin-margin retailers (COST, WMT, HD) that scores them on ROA/ROE, because their moat is inventory turns and not pricing power. |
| Valuation Fit | 20% | Forward P/E vs growth, 52-week range, owner-earnings yield benchmarked against the 10-year bond. |

The sector-aware piece does most of the work. Banks get routed through a ROE-based path because gross margin is meaningless for financials. Discount retailers get routed through ROA. Industrials clear the "strong moat" bar at 15% operating margin; tech has to hit 30% for the same credit.

Every override lives in one dictionary (`SECTOR_GM_BANDS`). When a ticker scores wrong, there's one place to fix it.

---

## The Munger Inversion

Every name is stress-tested against three killers:

1.  **Technology disruption.** Competitive leapfrog in the industry. Probability and fair-value impact vary by sector.
2.  **Debt spiral.** Anything over 4x debt/EBITDA fires at 30% probability, -40% FV impact, and caps the overall score at 6.0 regardless of how good the pillars look.
3.  **Governance failure.** Insider ownership below 1% fires at 20% probability, -30% FV impact.

If any killer crosses the red line, the Buffett score is capped at 6.0. Same discipline Charlie talks about in the "invert, always invert" lectures.

Today's scan flagged 57 high-score names with at least one material killer. The dashboard's Munger Inversion Alert section lists every one by ticker.

---

## The Audit That Almost Broke It

Before shipping, I spent an afternoon auditing the system like a skeptical outside buyer, not as the person who built it. Three failures I would have happily published:

*   **The "Munger Alert" section in the dashboard was a stub.** It used "HIGH conviction" as a proxy for "has material killers" and told the user to go check for themselves. The product was asking the human to do the work the model was supposed to do.
*   **Earnings predictability was the standard deviation of YoY changes**, which mathematically penalizes growth. A company going 30 → 40 → 50 has higher std-dev than one flat at 20 and was getting *penalized* for it. Separately, Lollapalooza counted "absence of material killers" as a positive force, which double-counts the inversion cap. And the dashboard masthead said "S&P 100 UNIVERSE" while showing 381 Russell 1000 names.
*   **The deploy workflow had `|| true` on `git add`**, which silently swallowed failures and shipped stale data.

I fixed each one, added the 22-test suite, and re-ran the audit clean. The remaining gap is empirical calibration (sector-peer percentile scoring, dynamic owner-earnings vs bond-yield cutoff), not leftover bugs.

---

## The Code

The full source (scoring engine, scanner, dashboard, unit tests, and the scheduled GitHub Actions workflow) lives in a Google Drive folder for paid subscribers: **[link]**.

Enough to run your own copy, tune the sector bands, or fork the scoring model in whatever direction your universe needs. If you want to extend it, the three places I'd start are (1) the `SECTOR_GM_BANDS` dictionary in `models/moat_lane.py`, (2) the retailer override in `RETAIL_SCALE_INDUSTRIES`, and (3) the inversion killer probability buckets. None of those are calibrated against historical data yet, and all of them are where a real edge would show up.

---

## What's Next

Live dashboard: **https://buffet-scanner.vercel.app**

The scanner runs every morning at 04:00 UTC. The dashboard updates itself. Tests run on every push.

The next piece I'm building is a factor-attribution layer that tells me which pillar moved a name up or down versus yesterday, so the daily diff is readable in ten seconds.

If there's a specific piece of the pipeline you want broken down (the sector-aware moat bands, the Munger inversion cap math, or the cyclicality penalty thresholds) reply to this post and I'll make it the next one.

---

*Built with Claude Code. If you're building something similar and want to compare notes, reply to this post. I read every one.*
