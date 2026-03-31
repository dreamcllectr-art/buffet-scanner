"""
Buffett/Munger Moat Lane Scorer
Quantitative + qualitative deep-dive: 4-pillar scoring, inversion analysis,
mental models checklist. Outputs moat_lane.md and appends buffett_premium
to signals_fusion.csv.

Usage: python3 models/moat_lane.py [TICKER]
"""

import yfinance as yf
import pandas as pd
import numpy as np
import os
import sys
from datetime import datetime, timedelta


# ---------------------------------------------------------------------------
# Circle of Competence gate
# ---------------------------------------------------------------------------
COMPETENCE_YES = [
    'Technology', 'Consumer', 'Communication Services', 'Financial Services',
    'Consumer Cyclical', 'Consumer Defensive', 'Industrials',
]
COMPETENCE_ASK = [
    'Healthcare', 'Biotechnology', 'Pharmaceutical', 'Energy', 'Utilities',
    'Basic Materials',
]


def classify_competence(sector, industry):
    """Return (in_circle: bool, note: str)."""
    for tag in COMPETENCE_YES:
        if tag.lower() in sector.lower() or tag.lower() in industry.lower():
            return True, f"In circle ({sector}/{industry})"
    for tag in COMPETENCE_ASK:
        if tag.lower() in sector.lower() or tag.lower() in industry.lower():
            return False, f"OUTSIDE circle — {sector}/{industry}. Proceed with caution."
    return False, f"Unknown sector ({sector}/{industry}) — flag for review."


# ---------------------------------------------------------------------------
# Pillar 1: Quality (30%)
# ---------------------------------------------------------------------------
def score_quality(ticker_sym, info, income, cashflow, balance):
    notes = []
    # Use a budget system: ROIC sets base (0-7), then modifiers add/subtract
    # within remaining headroom to 10. This prevents bonus stacking past ceiling.
    base_score = 5.0
    modifier = 0.0

    # --- ROIC history (use available years) ---
    try:
        ebit_series = income.loc['EBIT'] if 'EBIT' in income.index else None
        ic_series = balance.loc['Invested Capital'] if 'Invested Capital' in balance.index else None
        tax_rate = info.get('taxRate', 0.21) or 0.21

        if ebit_series is not None and ic_series is not None:
            roics = []
            for col in ebit_series.index:
                ebit = ebit_series[col]
                ic = ic_series[col] if col in ic_series.index else None
                if ic and ic > 0:
                    roics.append(ebit * (1 - tax_rate) / ic)
            if roics:
                avg_roic = np.mean(roics)
                if avg_roic > 0.25:
                    base_score = 7.0  # Ceiling for ROIC alone — leaves room for modifiers
                elif avg_roic > 0.15:
                    base_score = 5.5 + (avg_roic - 0.15) / 0.10 * 1.5
                else:
                    base_score = max(3.0, avg_roic / 0.15 * 5.5)
                # Declining trend penalty
                if len(roics) >= 3 and roics[0] < roics[-1] * 0.8:
                    modifier -= 2.0
                    notes.append("ROIC declining trend")
                notes.append(f"Avg ROIC: {avg_roic:.1%} ({len(roics)}y)")
        else:
            roic_single = info.get('returnOnEquity', 0) or 0
            if roic_single > 0.25:
                base_score = 6.5
            elif roic_single > 0.15:
                base_score = 5.0
            notes.append(f"Fallback ROE: {roic_single:.1%}")
    except Exception as e:
        notes.append(f"ROIC calc error: {e}")

    # --- Earnings predictability (critical for Buffett — penalize hard) ---
    try:
        net_income = income.loc['Net Income'] if 'Net Income' in income.index else None
        if net_income is not None and len(net_income) >= 3:
            yoy = net_income.pct_change(-1).dropna()
            std = yoy.std()
            if std < 0.10:
                modifier += 1.0
                notes.append(f"Earnings std: {std:.1%} (predictable)")
            elif std > 0.50:
                modifier -= 2.0  # Severe penalty for wild swings
                notes.append(f"Earnings std: {std:.1%} (highly volatile)")
            elif std > 0.20:
                modifier -= 1.0
                notes.append(f"Earnings std: {std:.1%} (volatile)")
            else:
                notes.append(f"Earnings std: {std:.1%}")
    except:
        pass

    # --- FCF conversion ---
    try:
        fcf = cashflow.loc['Free Cash Flow'] if 'Free Cash Flow' in cashflow.index else None
        ni = income.loc['Net Income'] if 'Net Income' in income.index else None
        if fcf is not None and ni is not None:
            conversion = (fcf / ni).mean()
            if conversion > 0.80:
                modifier += 1.0
                notes.append(f"FCF/NI: {conversion:.0%} (strong)")
            elif conversion < 0.50:
                modifier -= 0.5
                notes.append(f"FCF/NI: {conversion:.0%} (weak conversion)")
            else:
                notes.append(f"FCF/NI: {conversion:.0%}")
    except:
        pass

    # --- Gross margins ---
    gm = info.get('grossMargins', 0) or 0
    if gm > 0.50:
        modifier += 1.0
        notes.append(f"Gross margin: {gm:.0%} (pricing power)")
    elif gm < 0.30:
        modifier -= 0.5
        notes.append(f"Gross margin: {gm:.0%} (commodity-like)")
    else:
        notes.append(f"Gross margin: {gm:.0%}")

    score = min(10.0, max(0.0, base_score + modifier))
    return round(score, 1), "; ".join(notes)


# ---------------------------------------------------------------------------
# Pillar 2: Management (25%)
# ---------------------------------------------------------------------------
def score_management(ticker_sym, info, insider_df):
    notes = []
    score = 5.0

    # --- Insider ownership (adjust thresholds by market cap) ---
    # For mega-caps (>$500B), even 1-3% insider ownership = billions in skin-in-game
    # Raw percentage thresholds are misleading for large companies
    insider_pct = info.get('heldPercentInsiders', 0) or 0
    mc = info.get('marketCap', 0) or 0
    insider_value = insider_pct * mc

    if mc > 500e9:
        # Mega-cap: $5B+ insider value is strong alignment regardless of %
        if insider_value > 10e9:
            score = 9.0
            notes.append(f"Insider value: ${insider_value/1e9:.0f}B ({insider_pct:.1%}) — massive skin in game")
        elif insider_value > 1e9:
            score = 7.5
            notes.append(f"Insider value: ${insider_value/1e9:.1f}B ({insider_pct:.1%}) — significant")
        elif insider_pct > 0.01:
            score = 6.0
            notes.append(f"Insider ownership: {insider_pct:.1%} (${insider_value/1e9:.1f}B)")
        else:
            score = 4.5
            notes.append(f"Insider ownership: {insider_pct:.1%} — low for mega-cap")
    else:
        # Standard thresholds for smaller companies
        if insider_pct > 0.10:
            score = 9.0
            notes.append(f"Insider ownership: {insider_pct:.1%} (>10%)")
        elif insider_pct > 0.05:
            score = 7.0
            notes.append(f"Insider ownership: {insider_pct:.1%}")
        elif insider_pct > 0.01:
            score = 5.5
            notes.append(f"Insider ownership: {insider_pct:.1%} (low)")
        else:
            score = 4.0
            notes.append(f"Insider ownership: {insider_pct:.1%} (minimal)")

    # --- Recent insider activity ---
    if insider_df is not None and not insider_df.empty:
        try:
            cutoff = datetime.now() - timedelta(days=180)
            recent = insider_df[pd.to_datetime(insider_df['Start Date']) > cutoff]
            buys = recent[recent['Transaction'].str.contains('Buy|Purchase', case=False, na=False)]
            sells = recent[recent['Transaction'].str.contains('Sale|Sell', case=False, na=False)]
            if len(buys) > len(sells) and len(buys) >= 2:
                score += 1.0
                notes.append(f"Net insider buying ({len(buys)}B/{len(sells)}S last 6m)")
            elif len(sells) > len(buys) * 3:
                score -= 1.0
                notes.append(f"Heavy insider selling ({len(sells)}S vs {len(buys)}B)")
            else:
                notes.append(f"Insider activity: {len(buys)}B/{len(sells)}S last 6m")
        except:
            notes.append("Could not parse insider transactions")
    else:
        notes.append("No insider transaction data")

    # --- Share count (restricted stock as SBC proxy) ---
    shares = info.get('sharesOutstanding', 0)
    if shares:
        float_shares = info.get('floatShares', shares)
        if float_shares and shares:
            restricted_pct = 1 - (float_shares / shares)
            if restricted_pct > 0.05:
                score -= 0.5
                notes.append(f"Restricted stock: {restricted_pct:.1%} of shares (SBC concern)")
            else:
                notes.append(f"Restricted stock: {restricted_pct:.1%} (low)")

    score = min(10.0, max(0.0, score))
    return round(score, 1), "; ".join(notes)


# ---------------------------------------------------------------------------
# Pillar 3: Moat (25%)
# ---------------------------------------------------------------------------
def score_moat(ticker_sym, info, peer_df):
    notes = []
    score = 5.0

    # --- Gross margin as moat proxy ---
    gm = info.get('grossMargins', 0) or 0
    if gm > 0.60:
        score = 8.0
        notes.append(f"Gross margin {gm:.0%} — strong pricing power")
    elif gm > 0.40:
        score = 6.5
        notes.append(f"Gross margin {gm:.0%} — moderate moat")
    else:
        score = 4.0
        notes.append(f"Gross margin {gm:.0%} — weak pricing power")

    # --- Market share / dominance (revenue vs peers) ---
    if peer_df is not None and not peer_df.empty and 'Market Cap' in peer_df.columns:
        own_mc = info.get('marketCap', 0)
        peer_avg = peer_df['Market Cap'].mean()
        if own_mc and peer_avg and own_mc > peer_avg * 2:
            score += 1.5
            notes.append("Dominant market cap vs peers (>2x avg)")
        elif own_mc and peer_avg and own_mc > peer_avg:
            score += 0.5
            notes.append("Above-average market cap vs peers")

    # --- Operating margin stability (moat durability) ---
    om = info.get('operatingMargins', 0) or 0
    if om > 0.30:
        score += 1.0
        notes.append(f"Operating margin {om:.0%} — durable")
    elif om > 0.15:
        notes.append(f"Operating margin {om:.0%}")
    else:
        score -= 0.5
        notes.append(f"Operating margin {om:.0%} — thin")

    # --- Revenue growth consistency (switching costs proxy) ---
    rev_growth = info.get('revenueGrowth', 0) or 0
    if rev_growth > 0.20:
        score += 0.5
        notes.append(f"Rev growth {rev_growth:.0%} — demand pull")

    score = min(10.0, max(0.0, score))
    return round(score, 1), "; ".join(notes)


# ---------------------------------------------------------------------------
# Pillar 4: Valuation Fit (20%)
# ---------------------------------------------------------------------------
def score_valuation_fit(ticker_sym, info):
    notes = []
    score = 5.0

    # --- Forward P/E ---
    fwd_pe = info.get('forwardPE', None)
    trailing_pe = info.get('trailingPE', None)
    pe = fwd_pe or trailing_pe

    if pe:
        if pe < 15:
            score = 10.0
            notes.append(f"P/E {pe:.1f}x — deep value")
        elif pe < 20:
            score = 8.5
            notes.append(f"P/E {pe:.1f}x — fair price")
        elif pe < 30:
            score = 6.0
            notes.append(f"P/E {pe:.1f}x — growth premium")
        elif pe < 50:
            score = 4.0
            notes.append(f"P/E {pe:.1f}x — expensive")
        else:
            score = 2.0
            notes.append(f"P/E {pe:.1f}x — extreme premium")
    else:
        score = 3.0
        notes.append("No P/E data (unprofitable?)")

    # --- Price vs 52-week range (Mr. Market check) ---
    low52 = info.get('fiftyTwoWeekLow', None)
    high52 = info.get('fiftyTwoWeekHigh', None)
    price = info.get('currentPrice', None)
    if low52 and high52 and price:
        range_pct = (price - low52) / (high52 - low52) if high52 != low52 else 0.5
        if range_pct < 0.3:
            score += 1.5
            notes.append(f"Near 52w low ({range_pct:.0%} of range) — Mr. Market fearful")
        elif range_pct > 0.85:
            score -= 1.0
            notes.append(f"Near 52w high ({range_pct:.0%} of range) — Mr. Market greedy")
        else:
            notes.append(f"52w range position: {range_pct:.0%}")

    # --- Owner earnings yield ---
    fcf = info.get('freeCashflow', 0) or 0
    mc = info.get('marketCap', 0) or 0
    if fcf > 0 and mc > 0:
        oe_yield = fcf / mc
        if oe_yield > 0.05:
            score += 1.0
            notes.append(f"Owner earnings yield: {oe_yield:.1%} (>5%)")
        else:
            notes.append(f"Owner earnings yield: {oe_yield:.1%}")

    # --- vs index opportunity cost ---
    # Rough check: if earnings yield < 7% (index CAGR proxy), flag
    if pe and pe > 0:
        earnings_yield = 1 / pe
        if earnings_yield < 0.04:
            score -= 0.5
            notes.append("Earnings yield < 4% — worse than bonds")
        elif earnings_yield < 0.07:
            notes.append("Earnings yield < 7% — tight vs index")

    score = min(10.0, max(0.0, score))
    return round(score, 1), "; ".join(notes)


# ---------------------------------------------------------------------------
# Munger Inversion
# ---------------------------------------------------------------------------
def run_inversion(ticker_sym, info, quality_score, moat_score):
    """Generate 3 killers with probability and impact estimates."""
    killers = []

    # Killer 1: Technology disruption
    sector = info.get('sector', '')
    industry = info.get('industry', '')
    if any(x in sector.lower() or x in industry.lower() for x in ['tech', 'semi', 'software']):
        prob = 25
        impact = -35
        killers.append({
            'name': 'Technology Disruption',
            'description': f'Competitive leapfrog in {industry}',
            'probability': prob,
            'impact': impact,
            'material': prob >= 20 and abs(impact) >= 30,
        })
    else:
        killers.append({
            'name': 'Technology Disruption',
            'description': 'Low disruption risk for non-tech sector',
            'probability': 10,
            'impact': -15,
            'material': False,
        })

    # Killer 2: Debt spiral / capital misallocation
    debt_ebitda = info.get('totalDebt', 0) / info.get('ebitda', 1) if info.get('ebitda') else 0
    if debt_ebitda > 4:
        prob, impact = 30, -40
    elif debt_ebitda > 2:
        prob, impact = 15, -25
    else:
        prob, impact = 5, -10
    killers.append({
        'name': 'Debt Spiral / Capital Misallocation',
        'description': f'Debt/EBITDA: {debt_ebitda:.1f}x',
        'probability': prob,
        'impact': impact,
        'material': prob >= 20 and abs(impact) >= 30,
    })

    # Killer 3: Management / governance failure
    insider_pct = info.get('heldPercentInsiders', 0) or 0
    if insider_pct < 0.01:
        prob, impact = 20, -30
    elif insider_pct < 0.05:
        prob, impact = 15, -20
    else:
        prob, impact = 8, -15
    killers.append({
        'name': 'Management / Governance Failure',
        'description': f'Insider ownership {insider_pct:.1%}; key-man / succession risk',
        'probability': prob,
        'impact': impact,
        'material': prob >= 20 and abs(impact) >= 30,
    })

    # Cap rule: if any killer P>30% AND Impact>-30%, cap score at 6.0
    cap_triggered = any(k['probability'] > 30 and abs(k['impact']) > 30 for k in killers)

    return killers, cap_triggered


# ---------------------------------------------------------------------------
# Mental Models
# ---------------------------------------------------------------------------
def apply_mental_models(info, quality_score, moat_score, val_score, killers):
    models = []

    # Circle of Competence
    sector = info.get('sector', '')
    industry = info.get('industry', '')
    in_circle, note = classify_competence(sector, industry)
    models.append(('Circle of Competence', note))

    # Margin of Safety (growth-adjusted: use PEG-implied fair multiple)
    price = info.get('currentPrice', 0)
    eps = info.get('trailingEps', 0) or 0
    # earningsGrowth from yfinance is TTM quarterly YoY — one hot quarter can read 60-100%+.
    # Cap at 25% for multiple selection to avoid inflated IV from a single blowout quarter.
    raw_growth = info.get('earningsGrowth', 0) or info.get('revenueGrowth', 0) or 0
    earnings_growth = min(raw_growth, 0.25)
    if eps > 0:
        # Growth-adjusted multiple: 15x for 0% growth, up to 25x for >20% growth
        # This is Peter Lynch's PEG-inspired approach — Buffett pays more for growth
        if earnings_growth > 0.20:
            fair_multiple = 25
        elif earnings_growth > 0.10:
            fair_multiple = 20
        elif earnings_growth > 0.05:
            fair_multiple = 17
        else:
            fair_multiple = 15
        conservative_iv = eps * fair_multiple
        mos = (conservative_iv - price) / price if price > 0 else 0
        if mos > 0.30:
            models.append(('Margin of Safety', f'{mos:.0%} — PRESENT (IV ${conservative_iv:.0f} vs ${price:.0f} at {fair_multiple}x)'))
        elif mos > 0:
            models.append(('Margin of Safety', f'{mos:.0%} — thin (IV ${conservative_iv:.0f} at {fair_multiple}x)'))
        else:
            models.append(('Margin of Safety', f'{mos:.0%} — ABSENT (${price:.0f} > IV ${conservative_iv:.0f} at {fair_multiple}x for {earnings_growth:.0%} growth)'))
    else:
        models.append(('Margin of Safety', 'Cannot calculate (no positive EPS)'))

    # Lollapalooza (3+ forces aligning)
    forces = 0
    lolla_notes = []
    if quality_score >= 8:
        forces += 1
        lolla_notes.append("high quality")
    if moat_score >= 8:
        forces += 1
        lolla_notes.append("strong moat")
    if val_score >= 8:
        forces += 1
        lolla_notes.append("attractive valuation")
    rev_growth = info.get('revenueGrowth', 0) or 0
    if rev_growth > 0.20:
        forces += 1
        lolla_notes.append("secular growth")
    if not any(k['material'] for k in killers):
        forces += 1
        lolla_notes.append("no material killers")

    if forces >= 3:
        models.append(('Lollapalooza Effect', f'YES — {forces} forces aligning: {", ".join(lolla_notes)}'))
    else:
        models.append(('Lollapalooza Effect', f'No ({forces} forces only: {", ".join(lolla_notes) if lolla_notes else "none"})'))

    # Incentive-Caused Bias
    insider_pct = info.get('heldPercentInsiders', 0) or 0
    if insider_pct > 0.05:
        models.append(('Incentive-Caused Bias', f'Aligned — {insider_pct:.1%} insider ownership'))
    else:
        models.append(('Incentive-Caused Bias', f'Weak alignment — only {insider_pct:.1%} insider ownership'))

    # Mr. Market
    low52 = info.get('fiftyTwoWeekLow', 0) or 0
    high52 = info.get('fiftyTwoWeekHigh', 0) or 0
    price = info.get('currentPrice', 0) or 0
    if low52 and high52 and price:
        pos = (price - low52) / (high52 - low52) if high52 != low52 else 0.5
        if pos < 0.3:
            models.append(('Mr. Market', 'Fearful — potential opportunity'))
        elif pos > 0.85:
            models.append(('Mr. Market', 'Greedy — exercise caution'))
        else:
            models.append(('Mr. Market', 'Neutral'))

    return models


# ---------------------------------------------------------------------------
# Main Orchestrator
# ---------------------------------------------------------------------------
def run_moat_lane(ticker_sym):
    print(f"\n{'='*60}")
    print(f"  BUFFETT/MUNGER MOAT LANE: {ticker_sym}")
    print(f"{'='*60}\n")

    t = yf.Ticker(ticker_sym)
    info = t.info

    # Financials
    income = t.income_stmt
    balance = t.balance_sheet
    cashflow = t.cashflow

    # Insider data
    insider_df = None
    try:
        insider_df = t.insider_transactions
    except:
        pass

    # --- Detect yfinance insider misclassification ---
    # yfinance sometimes counts a large institutional holder (e.g. Berkshire Hathaway)
    # as "insiders" when their pct held ≈ heldPercentInsiders. Correct before scoring.
    try:
        inst_holders = t.institutional_holders
        if inst_holders is not None and len(inst_holders):
            top_inst_pct = float(inst_holders.iloc[0]['pctHeld'])
            reported_insider_pct = info.get('heldPercentInsiders', 0) or 0
            if reported_insider_pct > 0.05 and abs(top_inst_pct - reported_insider_pct) < 0.025:
                top_name = inst_holders.iloc[0]['Holder']
                print(f"WARNING: heldPercentInsiders ({reported_insider_pct:.1%}) matches top institutional "
                      f"holder {top_name} ({top_inst_pct:.1%}) — likely misclassification. Resetting to 0.")
                info = dict(info)  # make mutable copy
                info['heldPercentInsiders'] = 0.0
                info['_insider_misclassification_note'] = (
                    f"yfinance misclassified {top_name} ({top_inst_pct:.1%} inst.) as insider"
                )
    except Exception as e:
        pass

    # Peer data
    peer_df = None
    peer_path = f"{ticker_sym}/filings/peer_comps.csv"
    if os.path.exists(peer_path):
        peer_df = pd.read_csv(peer_path)

    # --- Circle of Competence Gate ---
    sector = info.get('sector', '')
    industry = info.get('industry', '')
    in_circle, circle_note = classify_competence(sector, industry)
    print(f"Circle of Competence: {circle_note}")
    if not in_circle:
        print("WARNING: Outside circle of competence. Proceeding with extra caution.\n")

    # --- Score Four Pillars ---
    q_score, q_notes = score_quality(ticker_sym, info, income, cashflow, balance)
    m_score, m_notes = score_management(ticker_sym, info, insider_df)
    moat_score, moat_notes = score_moat(ticker_sym, info, peer_df)
    v_score, v_notes = score_valuation_fit(ticker_sym, info)

    print(f"Quality:        {q_score}/10 — {q_notes}")
    print(f"Management:     {m_score}/10 — {m_notes}")
    print(f"Moat:           {moat_score}/10 — {moat_notes}")
    print(f"Valuation Fit:  {v_score}/10 — {v_notes}")

    # --- Munger Inversion ---
    killers, cap_triggered = run_inversion(ticker_sym, info, q_score, moat_score)
    print(f"\nInversion killers: {len([k for k in killers if k['material']])} material")

    # --- Weighted Score ---
    raw_score = (q_score * 0.30) + (m_score * 0.25) + (moat_score * 0.25) + (v_score * 0.20)
    if cap_triggered:
        raw_score = min(raw_score, 6.0)
        print("INVERSION CAP TRIGGERED: Score capped at 6.0")
    if not in_circle:
        raw_score = min(raw_score, 7.0)  # Penalty for outside competence

    buffett_score = round(raw_score, 1)

    # --- Alpha Adjustment & Conviction ---
    if buffett_score > 8.0:
        alpha_adj = 0.4
        conviction = 'HIGH'
        verdict = 'Own Forever'
    elif buffett_score > 6.0:
        alpha_adj = 0.1 + (buffett_score - 6.0) / 2.0 * 0.2
        conviction = 'MODERATE'
        verdict = 'Watchlist'
    elif buffett_score > 4.0:
        alpha_adj = 0.0
        conviction = 'LOW'
        verdict = 'Pass'
    else:
        alpha_adj = -0.2 - (4.0 - buffett_score) / 4.0 * 0.3
        conviction = 'AVOID'
        verdict = 'Avoid'

    alpha_adj = round(alpha_adj, 2)

    # --- Mental Models ---
    mental_models = apply_mental_models(info, q_score, moat_score, v_score, killers)

    # --- Lollapalooza flag ---
    lolla = [m for m in mental_models if m[0] == 'Lollapalooza Effect'][0][1]

    print(f"\nBUFFETT SCORE: {buffett_score}/10")
    print(f"Alpha Adjustment: {alpha_adj:+.2f}")
    print(f"Conviction: {conviction}")
    print(f"Verdict: {verdict}")

    # --- Generate Report ---
    report = generate_report(
        ticker_sym, info, buffett_score, alpha_adj, conviction, verdict,
        q_score, q_notes, m_score, m_notes, moat_score, moat_notes,
        v_score, v_notes, killers, mental_models, lolla, in_circle, circle_note
    )

    # Save
    os.makedirs(f"{ticker_sym}/outputs", exist_ok=True)
    report_path = f"{ticker_sym}/outputs/moat_lane.md"
    with open(report_path, 'w') as f:
        f.write(report)
    print(f"\nReport saved: {report_path}")

    # Merge buffett scores into signals_fusion.csv (preserve existing alt-data columns)
    fusion_path = f"{ticker_sym}/outputs/signals_fusion.csv"
    if os.path.exists(fusion_path):
        df = pd.read_csv(fusion_path)
        # Merge — don't overwrite existing columns
        df['buffett_premium'] = alpha_adj
        df['buffett_score'] = buffett_score
        # Recalculate composite to include buffett premium
        if 'Composite_Alpha' in df.columns:
            base_composite = df['Composite_Alpha'].iloc[0]
            df['Composite_Alpha_Adjusted'] = base_composite + (alpha_adj * 0.5)
        df.to_csv(fusion_path, index=False)
        print(f"Buffett premium merged into {fusion_path}")
    else:
        # No prior alt-data — create minimal file, flag that signals_gatherer should run first
        df = pd.DataFrame([{
            'Ticker': ticker_sym,
            'Composite_Alpha': 0.0,
            'buffett_premium': alpha_adj,
            'buffett_score': buffett_score,
            'Composite_Alpha_Adjusted': alpha_adj * 0.5,
        }])
        df.to_csv(fusion_path, index=False)
        print(f"Created {fusion_path} (note: run signals_gatherer.py for full alt-data)")

    return {
        'buffett_score': buffett_score,
        'alpha_adj': alpha_adj,
        'conviction': conviction,
        'verdict': verdict,
    }


def generate_report(ticker, info, score, alpha, conviction, verdict,
                    q_s, q_n, m_s, m_n, moat_s, moat_n, v_s, v_n,
                    killers, models, lolla, in_circle, circle_note):
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    price = info.get('currentPrice', 'N/A')
    mc = info.get('marketCap', 0)
    mc_str = f"${mc/1e9:.0f}B" if mc else 'N/A'

    misclass_note = info.get('_insider_misclassification_note', '')
    data_warnings = []
    if misclass_note:
        data_warnings.append(f"⚠ DATA: {misclass_note}")

    lines = [
        f"# Buffett/Munger Moat Lane: {ticker}",
        f"*Generated: {now} | Price: ${price} | Mkt Cap: {mc_str}*\n",
    ]
    if data_warnings:
        for w in data_warnings:
            lines.append(f"> {w}\n")
    lines += [
        f"## Circle of Competence: {'IN' if in_circle else 'OUTSIDE'}",
        f"{circle_note}\n",
        "---\n",
        "## Inversion First: What Could Kill This?\n",
        "| # | Killer | Description | Prob | Impact on FV | Material? |",
        "|---|--------|-------------|------|-------------|-----------|",
    ]
    for i, k in enumerate(killers, 1):
        mat = 'YES' if k['material'] else 'No'
        lines.append(f"| {i} | {k['name']} | {k['description']} | {k['probability']}% | {k['impact']}% | {mat} |")

    lines += [
        "\n---\n",
        "## Four-Pillar Score\n",
        "| Pillar | Score | Weight | Weighted | Rationale | Inversion Flag |",
        "|--------|-------|--------|----------|-----------|----------------|",
        f"| Quality | {q_s}/10 | 30% | {q_s*0.30:.1f} | {q_n} | {'ROIC declining' if 'declining' in q_n else '-'} |",
        f"| Management | {m_s}/10 | 25% | {m_s*0.25:.1f} | {m_n} | {'Heavy selling' if 'Heavy' in m_n else '-'} |",
        f"| Moat | {moat_s}/10 | 25% | {moat_s*0.25:.1f} | {moat_n} | {'Weak pricing' if 'weak' in moat_n.lower() else '-'} |",
        f"| Valuation Fit | {v_s}/10 | 20% | {v_s*0.20:.1f} | {v_n} | {'Expensive' if v_s < 5 else '-'} |",
        f"| **TOTAL** | **{score}/10** | **100%** | **{score}** | | |",
        "",
        f"## Buffett Score: {score} / 10",
        f"## Alpha Adjustment: {alpha:+.2f}",
        f"## Conviction: {conviction}",
        f"## Verdict: {verdict}\n",
        "---\n",
        "## Mental Models Applied\n",
    ]
    for name, finding in models:
        lines.append(f"- **{name}**: {finding}")

    lines += [
        "\n## Lollapalooza Check",
        f"{lolla}\n",
        "---\n",
        "## Alpha Thesis Integration",
        f"```",
        f"Buffett Premium: {alpha:+.2f} applied to composite alpha score",
        f"Conviction Gate: {conviction} — {'Proceed' if conviction in ('HIGH', 'MODERATE') else 'Do not initiate position'}",
        f"Half-life adjustment: {'None' if conviction == 'HIGH' else '+20% decay if MODERATE' if conviction == 'MODERATE' else 'N/A'}",
        f"```",
    ]

    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    ticker = sys.argv[1].upper() if len(sys.argv) > 1 else "NVDA"
    run_moat_lane(ticker)
