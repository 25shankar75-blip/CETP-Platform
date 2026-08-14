"""
CETP Digital Twin - Multi-Currency Financial Engine
File: financial_engine.py
"""

CURRENCY_RATES = {
    "INR (₹)": {"rate": 1.0, "symbol": "₹", "unit": "Crores"},
    "USD ($)": {"rate": 0.012, "symbol": "$", "unit": "M"},
    "EUR (€)": {"rate": 0.011, "symbol": "€", "unit": "M"},
    "AED (د.إ)": {"rate": 0.044, "symbol": "AED", "unit": "M"},
    "MYR (RM)": {"rate": 0.053, "symbol": "RM", "unit": "M"}
}

def format_currency(val_inr: float, currency_str: str) -> str:
    c_info = CURRENCY_RATES.get(currency_str, CURRENCY_RATES["INR (₹)"])
    rate = c_info["rate"]
    symbol = c_info["symbol"]
    
    val_converted = val_inr * rate
    
    if currency_str == "INR (₹)":
        val_cr = val_converted / 1e7
        return f"{symbol} {val_cr:.2f} Cr"
    else:
        val_m = val_converted / 1e6
        return f"{symbol} {val_m:.2f} M"

def calc_capex_breakup(scope: str, option_type: str, peak_tr: float, tes_trh: float, charge_chiller_tr: float, rates: dict):
    if scope == "Brownfield (Retrofit)" and option_type == "Conventional":
        return {
            "chiller_capex": 0.0,
            "brine_chiller_capex": 0.0,
            "tank_capex": 0.0,
            "medium_capex": 0.0,
            "phe_capex": 0.0,
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
        total_mep = chiller_capex * 1.2
        indirects = total_mep * rates.get("indirects_pct", 0.30)
        return {
            "chiller_capex": chiller_capex,
            "brine_chiller_capex": 0.0,
            "tank_capex": 0.0,
            "medium_capex": 0.0,
            "phe_capex": 0.0,
            "electrical_capex": chiller_capex * 0.15,
            "indirects": indirects,
            "total_capex": total_mep + indirects + (chiller_capex * 0.15)
        }
    elif option_type == "PCM TES":
        brine_chiller_capex = charge_chiller_tr * brine_rate
        tank_struct_capex = tes_trh * 2700.0
        pcm_medium_capex = tes_trh * 4800.0
        phe_capex = charge_chiller_tr * 1200.0
        mep_skids = (brine_chiller_capex + tank_struct_capex + pcm_medium_capex) * 0.12
        subtotal = brine_chiller_capex + tank_struct_capex + pcm_medium_capex + phe_capex + mep_skids
        indirects = subtotal * rates.get("indirects_pct", 0.30)
        return {
            "chiller_capex": 0.0,
            "brine_chiller_capex": brine_chiller_capex,
            "tank_capex": tank_struct_capex,
            "medium_capex": pcm_medium_capex,
            "phe_capex": phe_capex,
            "electrical_capex": brine_chiller_capex * 0.15,
            "indirects": indirects,
            "total_capex": subtotal + indirects
        }
    else:
        strat_tank_capex = tes_trh * strat_rate
        mep_skids = strat_tank_capex * 0.15
        subtotal = strat_tank_capex + mep_skids
        indirects = subtotal * rates.get("indirects_pct", 0.30)
        return {
            "chiller_capex": 0.0,
            "brine_chiller_capex": 0.0,
            "tank_capex": strat_tank_capex * 0.60,
            "medium_capex": strat_tank_capex * 0.05,
            "phe_capex": strat_tank_capex * 0.10,
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