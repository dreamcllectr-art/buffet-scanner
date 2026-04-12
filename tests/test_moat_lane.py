"""Unit tests for the Buffett/Munger scoring engine.

These tests exercise the pure scoring functions with synthetic inputs so they
can run without a network connection to Yahoo Finance. They cover:
  - Sector-aware moat scoring (fixes the bank/retailer penalty bug)
  - Earnings predictability direction (growth should earn the bonus)
  - Lollapalooza no-double-count (absence of killers does not add a force)
  - Inversion cap
  - Circle of Competence classification
  - Valuation fit edge cases

Run: pytest tests/ -v
"""

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from models.moat_lane import (
    classify_competence,
    score_quality,
    score_management,
    score_moat,
    score_valuation_fit,
    run_inversion,
    apply_mental_models,
)


# ---------------------------------------------------------------------------
# Helpers — build synthetic yfinance-shaped inputs
# ---------------------------------------------------------------------------

def _income_stmt(net_income_series, ebit_series=None):
    idx = [f"{2024 - i}-12-31" for i in range(len(net_income_series))]
    rows = {"Net Income": pd.Series(net_income_series, index=idx)}
    if ebit_series is not None:
        rows["EBIT"] = pd.Series(ebit_series, index=idx)
    return pd.DataFrame(rows).T


def _balance(invested_capital_series):
    idx = [f"{2024 - i}-12-31" for i in range(len(invested_capital_series))]
    return pd.DataFrame({"Invested Capital": pd.Series(invested_capital_series, index=idx)}).T


def _cashflow(fcf_series):
    idx = [f"{2024 - i}-12-31" for i in range(len(fcf_series))]
    return pd.DataFrame({"Free Cash Flow": pd.Series(fcf_series, index=idx)}).T


# ---------------------------------------------------------------------------
# Circle of Competence
# ---------------------------------------------------------------------------

class TestCircleOfCompetence:
    def test_technology_in_circle(self):
        ok, _ = classify_competence("Technology", "Software")
        assert ok is True

    def test_healthcare_outside_circle(self):
        ok, note = classify_competence("Healthcare", "Pharma")
        assert ok is False
        assert "OUTSIDE" in note

    def test_unknown_sector_flagged(self):
        ok, note = classify_competence("Widget Fabrication", "Widgets")
        assert ok is False
        assert "review" in note.lower()


# ---------------------------------------------------------------------------
# Earnings predictability — directional, not variance-based
# ---------------------------------------------------------------------------

class TestEarningsPredictability:
    """A growing company (30→40→50) should earn the predictability bonus.
    The old std-dev version penalized growth; the new version rewards
    monotonic direction."""

    def _base_info(self):
        return {
            "taxRate": 0.21,
            "grossMargins": 0.55,
            "returnOnEquity": 0.25,
        }

    def test_monotonic_growth_earns_bonus(self):
        # NI goes 30 → 40 → 50 → 60 (four up-years, zero down-years)
        income = _income_stmt([60, 50, 40, 30], ebit_series=[80, 70, 55, 40])
        balance = _balance([200, 180, 160, 140])
        cashflow = _cashflow([55, 45, 35, 25])
        score, notes = score_quality("TEST", self._base_info(), income, cashflow, balance)
        assert "predictable" in notes
        assert score >= 7.0  # high-quality growth

    def test_down_years_penalize(self):
        # NI goes 60 → 20 → 50 → 10 — choppy
        income = _income_stmt([10, 50, 20, 60], ebit_series=[15, 60, 30, 75])
        balance = _balance([150, 150, 150, 150])
        cashflow = _cashflow([10, 45, 15, 55])
        _, notes = score_quality("TEST", self._base_info(), income, cashflow, balance)
        assert "down-year" in notes


# ---------------------------------------------------------------------------
# Sector-aware moat scoring
# ---------------------------------------------------------------------------

class TestSectorAwareMoat:
    """Banks/retailers with structurally low GMs used to be auto-penalized.
    The sector-aware bands fix this."""

    def test_bank_with_strong_roe_scores_well(self):
        info = {
            "sector": "Financial Services",
            "grossMargins": 0.05,  # irrelevant for banks
            "operatingMargins": 0.35,
            "returnOnEquity": 0.18,
            "revenueGrowth": 0.05,
        }
        score, notes = score_moat("JPM", info, None)
        assert score >= 7.0
        assert "ROE" in notes

    def test_retailer_with_20pct_gm_not_auto_penalized(self):
        # COST-style: 12% gross margin is "normal strong" for Consumer Defensive
        info = {
            "sector": "Consumer Defensive",
            "grossMargins": 0.35,  # above the sector "moderate" cutoff of 0.30
            "operatingMargins": 0.05,
            "revenueGrowth": 0.08,
        }
        score, _ = score_moat("COST", info, None)
        # Was 4.0 under old thresholds; now should clear the moderate-moat bucket
        assert score >= 6.0

    def test_tech_with_high_gm_gets_strong_pricing_power(self):
        info = {
            "sector": "Technology",
            "grossMargins": 0.72,
            "operatingMargins": 0.38,
            "revenueGrowth": 0.22,
        }
        score, notes = score_moat("MSFT", info, None)
        assert score >= 8.5
        assert "strong pricing power" in notes

    def test_discount_retailer_scale_moat(self):
        """COST-style: 12% GM is structural. Moat should show via ROA/ROE,
        not be auto-penalized for thin gross margins."""
        info = {
            "sector": "Consumer Defensive",
            "industry": "Discount Stores",
            "grossMargins": 0.12,
            "operatingMargins": 0.035,
            "returnOnAssets": 0.09,
            "returnOnEquity": 0.28,
            "revenueGrowth": 0.08,
        }
        score, notes = score_moat("COST", info, None)
        assert score >= 7.0, f"Expected >=7.0, got {score}: {notes}"
        assert "scale moat" in notes

    def test_industrial_threshold_lower_than_tech(self):
        info_ind = {
            "sector": "Industrials",
            "grossMargins": 0.38,  # strong for industrial, weak for tech
            "operatingMargins": 0.16,
            "revenueGrowth": 0.05,
        }
        score_ind, _ = score_moat("CAT", info_ind, None)
        assert score_ind >= 7.0


# ---------------------------------------------------------------------------
# Lollapalooza — no double-counting for absence of killers
# ---------------------------------------------------------------------------

class TestLollapalooza:
    def _clean_info(self):
        return {
            "sector": "Technology",
            "industry": "Software",
            "heldPercentInsiders": 0.08,
            "currentPrice": 100.0,
            "trailingEps": 8.0,
            "earningsGrowth": 0.15,
            "fiftyTwoWeekLow": 80.0,
            "fiftyTwoWeekHigh": 120.0,
            "revenueGrowth": 0.12,
        }

    def test_absence_of_killers_does_not_add_force(self):
        """A borderline name (2 strong pillars, no killers, no growth) should
        NOT be marked Lollapalooza just because it has no killers."""
        info = self._clean_info()
        info["revenueGrowth"] = 0.08  # below the 20% secular-growth threshold
        killers = [  # all non-material
            {"name": "k1", "description": "", "probability": 5, "impact": -10, "material": False},
            {"name": "k2", "description": "", "probability": 5, "impact": -10, "material": False},
            {"name": "k3", "description": "", "probability": 5, "impact": -10, "material": False},
        ]
        # Two forces on: high quality (8) + strong moat (8), val only 7
        models = apply_mental_models(info, 8.0, 8.0, 7.0, killers)
        lolla = [m for m in models if m[0] == "Lollapalooza Effect"][0][1]
        # Old logic would score 3 forces (Q, moat, no-killers). New logic: 2.
        assert lolla.startswith("No"), f"Expected No, got: {lolla}"

    def test_lollapalooza_still_triggers_with_three_real_forces(self):
        info = self._clean_info()
        killers = [
            {"name": "k1", "description": "", "probability": 5, "impact": -10, "material": False},
        ]
        # Three positive forces: high Q, strong moat, cheap val
        models = apply_mental_models(info, 9.0, 9.0, 9.0, killers)
        lolla = [m for m in models if m[0] == "Lollapalooza Effect"][0][1]
        assert lolla.startswith("YES")


# ---------------------------------------------------------------------------
# Inversion — cap trigger
# ---------------------------------------------------------------------------

class TestInversion:
    def test_high_debt_triggers_cap(self):
        info = {
            "sector": "Industrials",
            "industry": "Machinery",
            "totalDebt": 1_000_000_000,
            "ebitda": 200_000_000,  # debt/ebitda = 5x
            "heldPercentInsiders": 0.08,
        }
        killers, cap_triggered = run_inversion("TEST", info, 8.0, 8.0)
        debt_killer = [k for k in killers if "Debt" in k["name"]][0]
        assert debt_killer["material"] is True
        assert cap_triggered is True

    def test_clean_balance_sheet_no_cap(self):
        info = {
            "sector": "Technology",
            "industry": "Software",
            "totalDebt": 0,
            "ebitda": 500_000_000,
            "heldPercentInsiders": 0.15,
        }
        killers, cap_triggered = run_inversion("TEST", info, 9.0, 9.0)
        # Tech disruption is always flagged as material for tech sector
        assert any(k["material"] for k in killers if "Technology" in k["name"])
        # But debt + governance killers should not fire
        non_tech = [k for k in killers if "Technology" not in k["name"]]
        assert not any(k["material"] for k in non_tech)


# ---------------------------------------------------------------------------
# Valuation fit
# ---------------------------------------------------------------------------

class TestValuationFit:
    def test_low_pe_scores_high(self):
        info = {
            "forwardPE": 12.0,
            "fiftyTwoWeekLow": 80.0,
            "fiftyTwoWeekHigh": 120.0,
            "currentPrice": 85.0,
            "freeCashflow": 10e9,
            "marketCap": 100e9,
        }
        score, _ = score_valuation_fit("TEST", info)
        assert score >= 9.0

    def test_extreme_pe_scores_low(self):
        info = {
            "forwardPE": 80.0,
            "fiftyTwoWeekLow": 80.0,
            "fiftyTwoWeekHigh": 120.0,
            "currentPrice": 115.0,
            "freeCashflow": 1e9,
            "marketCap": 500e9,
        }
        score, _ = score_valuation_fit("TEST", info)
        assert score <= 3.0

    def test_missing_pe_handled(self):
        info = {}
        score, notes = score_valuation_fit("TEST", info)
        assert score >= 0
        assert "No P/E" in notes


# ---------------------------------------------------------------------------
# Management — mega-cap dollar-adjusted
# ---------------------------------------------------------------------------

class TestManagement:
    def test_megacap_with_billions_insider_value_scores_high(self):
        info = {
            "heldPercentInsiders": 0.005,  # 0.5% of $3T = $15B
            "marketCap": 3_000e9,
            "sharesOutstanding": 1e10,
            "floatShares": 9.9e9,
        }
        score, notes = score_management("TEST", info, None)
        assert score >= 8.0
        assert "massive" in notes or "significant" in notes

    def test_megacap_with_zero_insider_penalized(self):
        info = {
            "heldPercentInsiders": 0.0,
            "marketCap": 1_000e9,
            "sharesOutstanding": 1e10,
            "floatShares": 1e10,
        }
        score, _ = score_management("TEST", info, None)
        assert score <= 5.0
