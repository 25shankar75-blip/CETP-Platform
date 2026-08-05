# financial_engine.py
from typing import Dict, Tuple
from schemas import CURRENCY_MULTIPLIERS

def format_currency(amount_inr: float, currency_key: str) -> str:
    cfg = CURRENCY_MULTIPLIERS.get(currency_key, CURRENCY_MULTIPLIERS["INR (₹)"])
    converted = amount_inr * cfg["rate"]
    sym = cfg["symbol"]
    if currency_key == "INR (₹)":
        if abs(converted) >= 10000000: return f"{sym} {converted / 10000000:.2f} Cr"
        elif abs(converted) >= 100000: return f"{sym} {converted / 100000:.2f} Lakhs"
        else: return f"{sym} {converted:,.0f}"
    else: return f"{sym} {converted:,.0f}"

def calculate_capex(b_cap: float, d_cap: float, t_cap: float, mode: str, prm: dict, dg_kva: float, base_inst: float, proj_type: str) -> Tuple[Dict[str, float], float]:
    is_brownfield = "Brownfield" in proj_type
    rates = prm.get('unit_rates', {})
    
    rate_chiller = rates.get('water_cooled_chiller', 19000) if "Water" in prm.get('chiller_type', 'Water') else rates.get('air_cooled_chiller', 21000)
    rate_brine = rates.get('brine_chiller', 23000)
    rate_ct = rates.get('cooling_tower', 3200)
    rate_pumps = rates.get('chw_pump', 900) + rates.get('cdw_pump', 650)
    rate_pcm = rates.get('pcm_cylindrical', 7800) if "Cylindrical" in prm.get('tank_shape', '') else rates.get('pcm_rectangular', 8500)
    rate_strat = rates.get('strat_tes', 18000)
    rate_elec = rates.get('dg_set', 11000) + rates.get('transformer', 1700)
    rate_phe = rates.get('phe', 1500)
    
    c_chill = 0.0 if is_brownfield else rate_chiller
    c_ct = 0.0 if is_brownfield else rate_ct
    c_pumps = 0.0 if is_brownfield else rate_pumps
    c_elec = 0.0 if is_brownfield else rate_elec
    
    bkup = {}
    if mode == "Conventional N+1":
        bkup['Base Chillers'] = base_inst * c_chill
        bkup['Dual/Brine Chillers'] = 0.0
        bkup['Towers & Pumps'] = base_inst * (c_ct + c_pumps)
        bkup['Storage Tank & Media'] = 0.0
        bkup['Electrical Infra & DG'] = dg_kva * c_elec
        sub_eq = bkup['Base Chillers'] + bkup['Towers & Pumps'] + bkup['Electrical Infra & DG']
        bkup['Indirects & Integration (30%)'] = sub_eq * prm.get('indirects_pct', 0.30)
    elif mode == "PCM TES Opt.":
        bkup['Base Chillers'] = b_cap * c_chill
        bkup['Dual/Brine Chillers'] = d_cap * rate_brine
        bkup['Towers & Pumps'] = (b_cap * (c_ct + c_pumps)) + (d_cap * (rate_ct + rate_pumps))
        bkup['Storage Tank & Media'] = t_cap * rate_pcm
        bkup['Electrical Infra & DG'] = dg_kva * c_elec
        sub_eq = bkup['Base Chillers'] + bkup['Dual/Brine Chillers'] + bkup['Towers & Pumps'] + bkup['Storage Tank & Media'] + bkup['Electrical Infra & DG'] + (t_cap * rate_phe)
        bkup['Indirects & Integration (30%)'] = sub_eq * prm.get('indirects_pct', 0.30)
    else: 
        bkup['Base Chillers'] = b_cap * c_chill
        bkup['Dual/Brine Chillers'] = 0.0
        bkup['Towers & Pumps'] = b_cap * (c_ct + c_pumps)
        bkup['Storage Tank & Media'] = t_cap * rate_strat
        bkup['Electrical Infra & DG'] = dg_kva * c_elec
        sub_eq = bkup['Base Chillers'] + bkup['Towers & Pumps'] + bkup['Storage Tank & Media'] + bkup['Electrical Infra & DG'] + (t_cap * rate_phe)
        bkup['Indirects & Integration (30%)'] = sub_eq * prm.get('indirects_pct', 0.30)
        
    return bkup, sum(bkup.values())