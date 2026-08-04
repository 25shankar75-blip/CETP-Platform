# financial_engine.py
from typing import Dict, Tuple
from schemas import CURRENCY_MULTIPLIERS

def format_currency(amount_inr: float, currency_key: str) -> str:
    cfg = CURRENCY_MULTIPLIERS.get(currency_key, CURRENCY_MULTIPLIERS["INR (₹)"])
    converted = amount_inr * cfg["rate"]
    sym = cfg["symbol"]
    
    if currency_key == "INR (₹)":
        if abs(converted) >= 10000000:
            return f"{sym} {converted / 10000000:.2f} Cr"
        elif abs(converted) >= 100000:
            return f"{sym} {converted / 100000:.2f} Lakhs"
        else:
            return f"{sym} {converted:,.0f}"
    else:
        return f"{sym} {converted:,.0f}"

def calculate_capex(b_cap: float, d_cap: float, t_cap: float, mode: str, prm: dict, dg_kva: float, base_inst: float, proj_type: str) -> Tuple[Dict[str, float], float]:
    is_brownfield = "Brownfield" in proj_type
    rates = prm.get('unit_rates', {})
    
    rate_chiller = rates.get('water_cooled_chiller', 17000) if "Water" in prm.get('chiller_type', 'Water') else rates.get('air_cooled_chiller', 19000)
    rate_brine = rates.get('brine_chiller', 23000)
    rate_ct = rates.get('cooling_tower', 2200)
    rate_pumps = rates.get('chw_pump', 700) + rates.get('cdw_pump', 550)
    rate_pcm = rates.get('pcm_tes_cylindrical', 7533) if "Cylindrical" in prm.get('tank_shape', '') else rates.get('pcm_tes_rectangular', 8475)
    rate_strat = rates.get('strat_tes', 18000)
    rate_elec = rates.get('dg_set', 11000) + rates.get('transformer', 1700)
    
    c_chill = 0.0 if is_brownfield else rate_chiller
    c_ct = 0.0 if is_brownfield else rate_ct
    
    bkup = {}
    if mode == "Conventional":
        bkup['Base Chillers'] = base_inst * c_chill
        bkup['Dual/Brine Chillers'] = 0.0
        bkup['Towers & Pumps'] = base_inst * (c_ct + rate_pumps)
        bkup['Storage Tank & Media'] = 0.0
        bkup['Electrical Infra & DG'] = dg_kva * rate_elec
        bkup['Piping & Indirects'] = (bkup['Base Chillers'] + bkup['Towers & Pumps']) * 0.15
    elif mode == "PCM TES":
        bkup['Base Chillers'] = b_cap * c_chill
        bkup['Dual/Brine Chillers'] = d_cap * rate_brine
        bkup['Towers & Pumps'] = (b_cap + d_cap) * (c_ct + rate_pumps)
        bkup['Storage Tank & Media'] = t_cap * rate_pcm
        bkup['Electrical Infra & DG'] = dg_kva * rate_elec
        bkup['Piping & Indirects'] = (bkup['Base Chillers'] + bkup['Dual/Brine Chillers'] + bkup['Towers & Pumps'] + bkup['Storage Tank & Media']) * 0.15
    else:
        bkup['Base Chillers'] = b_cap * c_chill
        bkup['Dual/Brine Chillers'] = 0.0
        bkup['Towers & Pumps'] = b_cap * (c_ct + rate_pumps)
        bkup['Storage Tank & Media'] = t_cap * rate_strat
        bkup['Electrical Infra & DG'] = dg_kva * rate_elec
        bkup['Piping & Indirects'] = (bkup['Base Chillers'] + bkup['Towers & Pumps'] + bkup['Storage Tank & Media']) * 0.15
        
    total = sum(bkup.values())
    return bkup, total