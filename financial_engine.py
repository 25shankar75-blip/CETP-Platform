"""
Cooling Energy Transition Platform (CETP) - Financial Engine
File: financial_engine.py
"""
import requests
from schemas import CURRENCY_MULTIPLIERS

def fetch_live_currency_rates() -> dict:
    try:
        resp = requests.get("https://open.er-api.com/v6/latest/INR", timeout=3).json()
        if resp.get("result") == "success":
            r = resp["rates"]
            return {
                "INR (₹)": {"rate": 1.0, "symbol": "₹", "unit": "Cr", "div": 1e7},
                "USD ($)": {"rate": r.get("USD", 0.012), "symbol": "$", "unit": "M", "div": 1e6},
                "EUR (€)": {"rate": r.get("EUR", 0.011), "symbol": "€", "unit": "M", "div": 1e6},
                "AED (د.إ)": {"rate": r.get("AED", 0.044), "symbol": "AED", "unit": "M", "div": 1e6},
                "MYR (RM)": {"rate": r.get("MYR", 0.053), "symbol": "RM", "unit": "M", "div": 1e6}
            }
    except Exception:
        pass 
    return CURRENCY_MULTIPLIERS

def format_currency(value_inr: float, currency_str: str, live_rates=None) -> str:
    if value_inr is None: return "-"
    rates = live_rates if live_rates else CURRENCY_MULTIPLIERS
    cfg = rates.get(currency_str, rates["INR (₹)"])
    return f"{cfg['symbol']} {(value_inr * cfg['rate']) / cfg['div']:.2f} {cfg['unit']}"