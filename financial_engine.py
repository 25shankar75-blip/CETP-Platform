"""
CETP Digital Twin - Financial & Costing Engine
File: financial_engine.py
"""
from schemas import CURRENCY_MULTIPLIERS

def format_currency(value_inr: float, currency_str: str) -> str:
    cfg = CURRENCY_MULTIPLIERS.get(currency_str, CURRENCY_MULTIPLIERS["INR (₹)"])
    converted = (value_inr * cfg["rate"]) / cfg["div"]
    return f"{cfg['symbol']} {converted:.2f} {cfg['unit']}"

def build_capex_breakdown(sys_type, scope, fleet_tr, tes_trh, charge_chiller_tr, rates):
    b = {"Chiller Equip.": 0, "TES Tank": 0, "PCM Media": 0, "Pumps & PHE": 0, "Electrical": 0}
    
    if sys_type == "Conventional":
        if scope == "Brownfield (Retrofit)": return {"Total CAPEX": 0.0, "Breakdown": b}
        b["Chiller Equip."] = fleet_tr * rates.base_chiller_rate
        b["Pumps & PHE"] = fleet_tr * 2500
        b["Electrical"] = fleet_tr * 1500
    
    elif sys_type == "PCM":
        b["Chiller Equip."] = charge_chiller_tr * rates.brine_chiller_rate
        b["TES Tank"] = tes_trh * 2800
        b["PCM Media"] = tes_trh * 4500
        b["Pumps & PHE"] = charge_chiller_tr * 3000
        b["Electrical"] = charge_chiller_tr * 1500
        
    elif sys_type == "Stratified":
        b["TES Tank"] = tes_trh * rates.stratified_tes_rate * 0.75
        b["Pumps & PHE"] = (tes_trh/8) * 1500
        b["Electrical"] = (tes_trh/8) * 1000

    subtotal = sum(b.values())
    total_capex = subtotal * (1.0 + rates.indirects_pct)
    return {"Total CAPEX": total_capex, "Breakdown": b}

def eval_payback(capex_delta, opex_savings):
    if opex_savings <= 0: return 99.9
    return capex_delta / opex_savings