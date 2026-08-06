def get_currency_multiplier(currency):
    rates = {
        "INR (₹)": 1.0, 
        "USD ($)": 0.012, 
        "EUR (€)": 0.011, 
        "AED (د.إ)": 0.044, 
        "MYR (RM)": 0.057
    }
    return rates.get(currency, 1.0)

def calculate_conventional_capex(installed_tr):
    return installed_tr * 45000 

def calculate_pcm_capex(trh, charge_chiller_tr):
    tank_capex = trh * 5500 
    chiller_capex = charge_chiller_tr * 65000 
    return tank_capex + chiller_capex

def calculate_stratified_capex(trh):
    return trh * 3500 

def apply_amc_and_indirects(mechanical_capex, static_tank_capex):
    mech_amc = mechanical_capex * 0.05
    tank_amc = static_tank_capex * 0.00
    indirects = (mechanical_capex + static_tank_capex) * 0.30
    return mech_amc + tank_amc, indirects

def simulate_opex(daily_load, tariff, dg_outage, tes_schedule, base_kw_tr=0.65):
    total_daily_opex = 0
    for h in range(24):
        # DG out-prices grid tariff if active
        cost_per_kwh = dg_outage[h] if dg_outage[h] > 0 else tariff[h]
        load = daily_load[h]
        
        if tes_schedule[h]['discharge']:
            # Pumping power only (Chillers are off or ramped down)
            kw = load * base_kw_tr * 0.1 
        elif tes_schedule[h]['charge']:
            # Base load + charging penalty
            kw = load * base_kw_tr * 1.2 
        else:
            # Standard operation
            kw = load * base_kw_tr
            
        total_daily_opex += kw * cost_per_kwh
        
    return total_daily_opex * 365