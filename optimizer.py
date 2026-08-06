def optimize_tes_capacity(daily_load_profile, tariff_profile, dg_outage_hours, scope, chiller_fleet, financial_rates):
    """
    Iterates through TES capacities (TRh) to MAXIMIZE OPEX savings while strictly 
    maintaining ROI < 3 to 4 years. Capable of scaling to 3017 TRh / 4950 TRh limits.
    """
    total_daily_trh = sum(daily_load_profile)
    max_search_trh = total_daily_trh * 0.85 # Search up to 85% of daily load for maximum shift
    
    # Calculate existing plant capacity for stratified constraints
    installed_chiller_tr = sum([unit['Capacity (TR)'] * unit['Quantity'] for unit in chiller_fleet]) 
    
    best_pcm_scenario = None
    best_pcm_opex_savings = -1
    
    best_strat_scenario = None
    best_strat_opex_savings = -1

    # Sunk Cost Logic for Retrofit
    baseline_capex = 0.0 if scope == "Retrofit (Brownfield)" else calculate_conventional_capex(installed_chiller_tr)
    baseline_opex = simulate_conventional_opex(daily_load_profile, tariff_profile, dg_outage_hours, installed_chiller_tr)

    # Step through TRh aggressively (steps of 200 TRh allows scaling up to 4950 TRh efficiently)
    for test_trh in range(500, int(max_search_trh), 200):
        
        # --- PCM Evaluation (Requires Dedicated Brine Chiller) ---
        pcm_charge_chiller_tr = (test_trh / 8.0) * 1.15 # Sized strictly for 8-hour off-peak window + FOM
        pcm_capex = calculate_pcm_capex(test_trh, pcm_charge_chiller_tr) 
        pcm_opex = simulate_pcm_opex(daily_load_profile, tariff_profile, dg_outage_hours, test_trh, pcm_charge_chiller_tr)
        
        pcm_savings = baseline_opex - pcm_opex
        pcm_incremental_capex = pcm_capex - baseline_capex
        
        if pcm_savings > 0:
            pcm_roi = pcm_incremental_capex / pcm_savings
            # Objective: Maximize absolute OPEX cashflow within ROI limit
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

        # --- Stratified Evaluation (Uses Existing Fleet Spare Capacity) ---
        strat_capex = calculate_stratified_capex(test_trh) # No new chiller CAPEX for retrofit
        strat_opex = simulate_stratified_opex(daily_load_profile, tariff_profile, dg_outage_hours, test_trh, installed_chiller_tr)
        
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