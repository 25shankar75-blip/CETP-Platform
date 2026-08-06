def optimize_tes_capacity(daily_load_profile, tariff_profile, scope, chiller_fleet, financial_rates):
    """
    Iterates through TES capacities (TRh) to MAXIMIZE OPEX savings while strictly 
    maintaining ROI < 3 to 4 years. Forces Dedicated Charge Chiller for PCM.
    """
    total_daily_trh = sum(daily_load_profile)
    max_search_trh = total_daily_trh * 0.85 # Search up to 85% of daily load for maximum shift
    
    best_pcm_scenario = None
    best_pcm_opex_savings = -1
    
    best_strat_scenario = None
    best_strat_opex_savings = -1

    # Sunk Cost Logic for Retrofit
    baseline_capex = 0.0 if scope == "Retrofit" else calculate_conventional_capex(chiller_fleet)
    baseline_opex = simulate_conventional_opex(daily_load_profile, tariff_profile, chiller_fleet)

    # Step through TRh sizes aggressively (steps of 200 TRh)
    for test_trh in range(500, int(max_search_trh), 200):
        
        # --- PCM Evaluation (Requires Dedicated Brine Chiller) ---
        # Charge chiller strictly sized to handle the entire test_trh in an 8-hour off-peak window
        pcm_charge_chiller_tr = (test_trh / 8.0) * 1.15 # 15% safety/FOM margin
        pcm_capex = calculate_pcm_capex(test_trh, pcm_charge_chiller_tr) 
        pcm_opex = simulate_pcm_opex(daily_load_profile, tariff_profile, test_trh, pcm_charge_chiller_tr)
        
        pcm_savings = baseline_opex - pcm_opex
        pcm_incremental_capex = pcm_capex - baseline_capex
        
        if pcm_savings > 0:
            pcm_roi = pcm_incremental_capex / pcm_savings
            # Objective: Maximize OPEX savings while ROI is acceptable
            if pcm_roi <= 4.0 and pcm_savings > best_pcm_opex_savings:
                best_pcm_opex_savings = pcm_savings
                best_pcm_scenario = {
                    "trh": test_trh, 
                    "charge_chiller_tr": pcm_charge_chiller_tr,
                    "capex": pcm_capex, 
                    "opex": pcm_opex, 
                    "roi": pcm_roi
                }

        # --- Stratified Evaluation (Uses Existing Fleet Spare Capacity) ---
        strat_capex = calculate_stratified_capex(test_trh) # No new chiller CAPEX
        strat_opex = simulate_stratified_opex(daily_load_profile, tariff_profile, test_trh, chiller_fleet)
        
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
                    "roi": strat_roi
                }

    return best_pcm_scenario, best_strat_scenario, baseline_opex