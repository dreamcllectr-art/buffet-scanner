"""
Buffett/Munger Universe Scanner
Runs moat_lane scoring across a ticker universe, ranks by Buffett score.

Usage:
  python3 scanner.py                      # S&P 500 + Russell 1000 (default)
  python3 scanner.py --universe sp100     # S&P 100 only
  python3 scanner.py --universe sp500     # S&P 500 only
  python3 scanner.py --universe russell   # Russell 1000 only
  python3 scanner.py --tickers AAPL MSFT  # custom list
  python3 scanner.py --top 20 --workers 12
"""

import sys
import os
import argparse
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

# Add project root so moat_lane is importable
sys.path.insert(0, os.path.dirname(__file__))
from models.moat_lane import run_moat_lane

# ---------------------------------------------------------------------------
# Universe fetchers
# ---------------------------------------------------------------------------
SP100 = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "BRK-B", "JPM", "LLY",
    "V", "UNH", "XOM", "MA", "JNJ", "PG", "HD", "AVGO", "COST", "MRK",
    "ABBV", "CVX", "KO", "PEP", "ADBE", "WMT", "MCD", "CRM", "BAC", "TMO",
    "ACN", "CSCO", "ABT", "LIN", "NFLX", "TXN", "AMD", "NEE", "PM", "WFC",
    "ORCL", "DHR", "DIS", "INTC", "AMGN", "UPS", "INTU", "QCOM", "IBM", "CAT",
    "AMAT", "LOW", "HON", "GS", "SBUX", "ELV", "RTX", "SPGI", "AXP", "MS",
    "BLK", "NOW", "PLD", "MDLZ", "T", "DE", "GILD", "ADI", "BKNG", "VRTX",
    "SYK", "REGN", "ZTS", "MMC", "MO", "ADP", "LRCX", "CB", "BSX", "C",
    "SO", "CME", "CI", "ISRG", "TJX", "DUK", "NOC", "AON", "PNC", "USB",
    "ITW", "EOG", "HUM", "MMM", "SHW", "MCO", "F", "GM", "FDX", "KHC",
]


def fetch_sp500():
    """Pull current S&P 500 constituents from Wikipedia."""
    try:
        import requests, io
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; buffet-scanner/1.0)'}
        html = requests.get(
            'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies',
            headers=headers, timeout=15
        ).text
        tables = pd.read_html(io.StringIO(html))
        tickers = tables[0]['Symbol'].tolist()
        return [t.replace('.', '-') for t in tickers]
    except Exception as e:
        print(f"Warning: could not fetch S&P 500 from Wikipedia ({e}), falling back to SP100")
        return SP100


def fetch_russell1000():
    """Pull Russell 1000 constituents from iShares IWB holdings CSV (updated monthly)."""
    try:
        url = 'https://www.ishares.com/us/products/239707/ishares-russell-1000-etf/1467271812596.ajax?fileType=csv&fileName=IWB_holdings&dataType=fund'
        df = pd.read_csv(url, skiprows=9)
        df.columns = df.columns.str.strip()
        # Keep equity rows only (exclude cash, futures)
        tickers = df[df['Asset Class'] == 'Equity']['Ticker'].dropna().tolist()
        tickers = [str(t).strip().replace('.', '-') for t in tickers if str(t).strip() not in ('', '-', 'nan')]
        return tickers
    except Exception as e:
        print(f"Warning: could not fetch Russell 1000 from iShares ({e}), falling back to SP500")
        return fetch_sp500()


def get_universe(name):
    if name == 'sp100':
        return SP100
    if name == 'sp500':
        return fetch_sp500()
    if name == 'russell':
        return fetch_russell1000()
    # Default: S&P 500 + Russell 1000 deduplicated
    sp500 = fetch_sp500()
    russell = fetch_russell1000()
    combined = list(dict.fromkeys(sp500 + russell))  # preserve order, dedupe
    print(f"Universe: {len(sp500)} S&P 500 + {len(russell)} Russell 1000 = {len(combined)} unique tickers")
    return combined


def scan_ticker(sym):
    """Run moat_lane on a single ticker. Returns dict or None on failure."""
    try:
        result = run_moat_lane(sym)
        result['ticker'] = sym
        return result
    except Exception as e:
        return {'ticker': sym, 'error': str(e)}


def run_scan(tickers, workers=8, verbose=False):
    results = []
    errors = []

    if not verbose:
        # Suppress stdout from moat_lane during scan
        import io
        from contextlib import redirect_stdout

        def scan_silent(sym):
            with redirect_stdout(io.StringIO()):
                return scan_ticker(sym)
        fn = scan_silent
    else:
        fn = scan_ticker

    print(f"Scanning {len(tickers)} tickers with {workers} workers...\n")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fn, sym): sym for sym in tickers}
        done = 0
        for f in as_completed(futures):
            done += 1
            sym = futures[f]
            r = f.result()
            if r and 'error' not in r:
                results.append(r)
                score = r['buffett_score']
                verdict = r['verdict']
                bar = '█' * int(score) + '░' * (10 - int(score))
                print(f"  [{done:3d}/{len(tickers)}] {sym:<6} {bar} {score:.1f}  {verdict}")
            else:
                err = r.get('error', 'unknown') if r else 'unknown'
                errors.append(sym)
                print(f"  [{done:3d}/{len(tickers)}] {sym:<6} ERROR: {err[:60]}")

    return results, errors


def print_leaderboard(results, top_n):
    ranked = sorted(results, key=lambda x: x['buffett_score'], reverse=True)
    top = ranked[:top_n]

    print(f"\n{'='*72}")
    print(f"  BUFFETT/MUNGER LEADERBOARD — Top {top_n} of {len(results)}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*72}")
    print(f"  {'#':<4} {'Ticker':<8} {'Score':>6} {'Alpha':>7} {'Conviction':<12} {'Verdict'}")
    print(f"  {'-'*64}")

    for i, r in enumerate(top, 1):
        score = r['buffett_score']
        alpha = r['alpha_adj']
        conviction = r['conviction']
        verdict = r['verdict']
        sym = r['ticker']

        # Color coding via unicode blocks
        if score >= 8.5:
            marker = '★★★'
        elif score >= 7.5:
            marker = '★★ '
        elif score >= 6.5:
            marker = '★  '
        else:
            marker = '   '

        print(f"  {i:<4} {sym:<8} {score:>5.1f}  {alpha:>+6.2f}  {conviction:<12} {verdict}  {marker}")

    # Summary stats
    scores = [r['buffett_score'] for r in results]
    own_forever = [r for r in results if r['verdict'] == 'Own Forever']
    watchlist = [r for r in results if r['verdict'] == 'Watchlist']

    print(f"\n  Universe stats: avg {sum(scores)/len(scores):.1f} | "
          f"Own Forever: {len(own_forever)} | Watchlist: {len(watchlist)} | "
          f"Pass/Avoid: {len(results) - len(own_forever) - len(watchlist)}")
    print(f"{'='*72}\n")

    return ranked


def save_results(ranked, output_path):
    # Rotate previous results before overwriting
    prev_path = output_path.replace('.csv', '_prev.csv')
    if os.path.exists(output_path):
        import shutil
        shutil.copy2(output_path, prev_path)

    rows = []
    for r in ranked:
        rows.append({
            'ticker': r['ticker'],
            'buffett_score': r['buffett_score'],
            'alpha_adj': r['alpha_adj'],
            'conviction': r['conviction'],
            'verdict': r['verdict'],
        })
    df = pd.DataFrame(rows)
    df.to_csv(output_path, index=False)
    print(f"Full results saved: {output_path}")
    if os.path.exists(prev_path):
        print(f"Previous results preserved: {prev_path}")


def main():
    parser = argparse.ArgumentParser(description='Buffett/Munger Universe Scanner')
    parser.add_argument('--tickers', nargs='+', help='Custom ticker list')
    parser.add_argument('--universe', default='all', choices=['all', 'sp100', 'sp500', 'russell'],
                        help='Universe to scan (default: sp500+russell1000)')
    parser.add_argument('--top', type=int, default=20, help='Show top N results (default: 20)')
    parser.add_argument('--workers', type=int, default=8, help='Parallel workers (default: 8)')
    parser.add_argument('--verbose', action='store_true', help='Show full moat_lane output per ticker')
    parser.add_argument('--output', default='scan_results.csv', help='Output CSV path')
    args = parser.parse_args()

    tickers = args.tickers if args.tickers else get_universe(args.universe)

    results, errors = run_scan(tickers, workers=args.workers, verbose=args.verbose)

    if not results:
        print("No results. Check your internet connection or ticker symbols.")
        return

    ranked = print_leaderboard(results, min(args.top, len(results)))

    output_path = os.path.join(os.path.dirname(__file__), args.output)
    save_results(ranked, output_path)

    if errors:
        print(f"Failed tickers ({len(errors)}): {', '.join(errors)}")


if __name__ == '__main__':
    main()
