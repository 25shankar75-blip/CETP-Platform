"""
Cooling Energy Transition Platform (CETP) - Multi-Currency & Financial Engine
File: financial_engine.py
"""

import urllib.request
import json
from schemas import CURRENCY_MULTIPLIERS

CURRENCY_RATES_DEFAULT = CURRENCY_MULTIPLIERS

def fetch_live_currency_rates() -> dict:
    """Fetch live exchange rates from Open Exchange Rates API with fallback."""
    try:
        url = "https://open.er-api.com/v6/latest/INR"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=3) as response:
            data = json.loads(response.read().decode())
            r = data["rates"]
            return {
                "INR (₹)": {"rate": 1.0, "symbol": "₹", "unit": "Crores", "div": 1e7},
                "USD ($)": {"rate": r.get("USD", 0.012), "symbol": "$", "unit": "M", "div": 1e6},
                "EUR (€)": {"rate": r.get("EUR", 0.011), "symbol": "€", "unit": "M", "div": 1e6},
                "AED (د.إ)": {"rate": r.get("AED", 0.044), "symbol": "AED", "unit": "M", "div": 1e6},
                "MYR (RM)": {"rate": r.get("MYR", 0.053), "symbol": "RM", "unit": "M", "div": 1e6}
            }
    except Exception:
        return CURRENCY_RATES_DEFAULT

def format_currency(val_inr: float, currency_str: str, live_rates: dict = None) -> str:
    rates = live_rates if live_rates else CURRENCY_RATES_DEFAULT
    c_info = rates.get(currency_str, CURRENCY_RATES_DEFAULT["INR (₹)"])
    rate = c_info["rate"]
    symbol = c_info["symbol"]
    unit = c_info.get("unit", "Crores")
    div = c_info.get("div", 1e7)
    
    val_converted = (val_inr * rate) / div
    return f"{symbol} {val_converted:.2f} {unit}"

def calc_capex_breakup(scope: str, option_type: str, peak_tr: float, tes_trh: float, charge_chiller_tr: float, rates: dict):
    """Calculates Turnkey CAPEX line-item breakdown. Sets Baseline Mechanical CAPEX = ₹0.00 for Retrofits."""
    if scope == "Brownfield (Retrofit)" and option_type == "Conventional":
        return {
            "chiller_capex": 0.0,
            "brine_chiller_capex": 0.0,
            "tank_capex": 0.0,
            "medium_capex": 0.0,
            "phe_capex": 0.0,
            "pumps_ct_capex": 0.0,
            "electrical_capex": 0.0,
            "indirects": 0.0,
            "total_capex": 0.0
        }
        
    base_rate = rates.get("base_chiller_rate_per_tr", 22000.0)
    brine_rate = rates.get("brine_chiller_rate_per_tr", 25000.0)
    pcm_rate = rates.get("pcm_tes_rate_per_trh", 7800.0)
    strat_rate = rates.get("stratified_tes_rate_per_trh", 18000.0)
    
    if option_type == "Conventional":
        installed_tr = peak_tr * 1.25
        chiller_capex = installed_tr * base_rate
        pumps_ct = installed_tr * 3500.0
        total_mep = chiller_capex + pumps_ct
        indirects = total_mep * rates.get("indirects_pct", 0.30)
        return {
            "chiller_capex": chiller_capex,
            "brine_chiller_capex": 0.0,
            "tank_capex": 0.0,
            "medium_capex": 0.0,
            "phe_capex": 0.0,
            "pumps_ct_capex": pumps_ct,
            "electrical_capex": total_mep * 0.15,
            "indirects": indirects,
            "total_capex": total_mep + indirects + (total_mep * 0.15)
        }
    elif option_type == "PCM TES":
        brine_chiller_capex = charge_chiller_tr * brine_rate
        tank_struct_capex = tes_trh * 2700.0
        pcm_medium_capex = tes_trh * 4800.0
        phe_capex = charge_chiller_tr * 1200.0
        pumps_ct = charge_chiller_tr * 2500.0
        subtotal = brine_chiller_capex + tank_struct_capex + pcm_medium_capex + phe_capex + pumps_ct
        indirects = subtotal * rates.get("indirects_pct", 0.30)
        return {
            "chiller_capex": 0.0,
            "brine_chiller_capex": brine_chiller_capex,
            "tank_capex": tank_struct_capex,
            "medium_capex": pcm_medium_capex,
            "phe_capex": phe_capex,
            "pumps_ct_capex": pumps_ct,
            "electrical_capex": brine_chiller_capex * 0.15,
            "indirects": indirects,
            "total_capex": subtotal + indirects
        }
    else:
        strat_tank_capex = tes_trh * strat_rate
        pumps_ct = (tes_trh / 8.0) * 2200.0
        subtotal = strat_tank_capex + pumps_ct
        indirects = subtotal * rates.get("indirects_pct", 0.30)
        return {
            "chiller_capex": 0.0,
            "brine_chiller_capex": 0.0,
            "tank_capex": strat_tank_capex * 0.65,
            "medium_capex": strat_tank_capex * 0.05,
            "phe_capex": strat_tank_capex * 0.10,
            "pumps_ct_capex": pumps_ct,
            "electrical_capex": strat_tank_capex * 0.10,
            "indirects": indirects,
            "total_capex": subtotal + indirects
        }

def calc_payback_and_roi(capex_delta: float, opex_savings_annual: float):
    if opex_savings_annual <= 0:
        return 99.0, 0.0
    payback_years = capex_delta / opex_savings_annual
    roi_pct = (opex_savings_annual / max(1.0, capex_delta)) * 100.0
    return payback_years, roi_pct

def eval_payback(capex_delta: float, opex_savings_annual: float):
    """Wrapper for payback evaluation."""
    pb, _ = calc_payback_and_roi(capex_delta, opex_savings_annual)
    return pb