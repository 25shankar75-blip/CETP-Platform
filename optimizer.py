from financial_engine import calculate_conventional_capex, calculate_pcm_capex, calculate_stratified_capex, simulate_opex
from physics_engine import get_dispatch_schedule

def optimize_tes_capacity(daily_load_profile, tariff_profile, dg_outage_hours, scope, chiller_fleet, currency):
    total_daily_trh = sum(daily_load_profile)
    max_search_trh = total_daily_trh * 0.85 
    
    # Calculate installed plant TR from user array
    installed_chiller_tr = sum([unit['Capacity (TR)'] * unit['Quantity'] for unit in chiller_fleet]) 
    
    best_pcm_scenario = {"trh": 0, "capex": 0, "opex": 9999999999, "savings": 0, "roi": 999, "charge_chiller_tr": 0}
    best_strat_scenario = {"trh": 0, "capex": 0, "opex": 9999999999, "savings": 0, "roi": 999}
    
    best_pcm_opex_savings = -1
    best_strat_opex_savings = -1

    # Apply Sunk Cost Logic for Retrofits (Baseline CAPEX is forced to 0.0)
    baseline_capex = 0.0 if scope == "Retrofit (Brownfield)" else calculate_conventional_capex(installed_chiller_tr)
    conv_schedule = [{"charge": False, "discharge": False} for _ in range(24)]
    baseline_opex = simulate_opex(daily_load_profile, tariff_profile, dg_outage_hours, conv_schedule)

    # Aggressively explore capacities up to 85% of load
    for test_trh in range(500, int(max_search_trh), 200):
        
        # --- PCM Evaluation ---
        pcm_charge_chiller_tr = (test_trh / 8.0) * 1.15 
        pcm_capex = calculate_pcm_capex(test_trh, pcm_charge_chiller_tr) 
        pcm_schedule = get_dispatch_schedule(daily_load_profile, tariff_profile, dg_outage_hours, installed_chiller_tr, "PCM")
        pcm_opex = simulate_opex(daily_load_profile, tariff_profile, dg_outage_hours, pcm_schedule)
        
        pcm_savings = baseline_opex - pcm_opex
        pcm_incremental_capex = pcm_capex - baseline_capex
        
        if pcm_savings > 0:
            pcm_roi = pcm_incremental_capex / pcm_savings
            if pcm_roi <= 4.0 and pcm_savings > best_pcm_opex_savings:
                best_pcm_opex_savings = pcm_savings
                best_pcm_scenario = {
                    "trh": test_trh, 
                    "charge_chiller_tr": pcm_charge_chiller_tr,
                    "capex": pcm_capex, 
                    "opex": pcm_opex,
                    "savings": pcm_savings,
                    "roi": pcm_roi
                }

        # --- Stratified Evaluation ---
        strat_capex = calculate_stratified_capex(test_trh) 
        strat_schedule = get_dispatch_schedule(daily_load_profile, tariff_profile, dg_outage_hours, installed_chiller_tr, "Stratified")
        strat_opex = simulate_opex(daily_load_profile, tariff_profile, dg_outage_hours, strat_schedule)
        
        strat_savings = baseline_opex - strat_opex
        strat_incremental_capex = strat_capex - baseline_capex
        
        if strat_savings > 0:
            strat_roi = strat_incremental_capex / strat_savings
            if strat_roi <= 4.0 and strat_savings > best_strat_opex_savings:
                best_strat_opex_savings = strat_savings
                best_strat_scenario = {
                    "trh": test_trh,
                    "capex": strat_capex,
                    "opex": strat_opex,
                    "savings": strat_savings,
                    "roi": strat_roi
                }

    return best_pcm_scenario, best_strat_scenario, baseline_opex, baseline_capex