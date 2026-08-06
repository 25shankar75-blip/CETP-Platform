"""
Cooling Energy Transition Platform (CETP) - Iterative OPEX Maximizer
File: optimizer.py
"""

import numpy as np
import pandas as pd
from physics_engine import simulate_24h_plant, simulate_pcm_tes_24h, simulate_stratified_tes_24h
from financial_engine import calc_capex_breakup, calc_payback_and_roi

def optimize_tes_plant(df_24h: pd.DataFrame, scope: str, peak_tr: float, audit_config: dict, rates: dict, fleet_df: pd.DataFrame):
    """Iteratively searches storage capacities to maximize annual OPEX savings targeting an optimal payback near 2 years (< 4 yrs hard filter)."""
    base_sim = simulate_24h_plant(df_24h, scope, audit_config, fleet_df=fleet_df)
    base_capex = calc_capex_breakup(scope, "Conventional", peak_tr, 0, 0, rates)["total_capex"]
    base_opex = base_sim["annual_opex"]
    
    max_search_trh = min(25000.0, peak_tr * 12.0)
    test_capacities = np.linspace(500.0, max_search_trh, 25)
    
    # 1. PCM TES Optimization Search
    best_pcm = None
    best_pcm_savings = -1e9
    
    for tes_trh in test_capacities:
        charge_chiller_tr = tes_trh / 8.0 # 8-Hour continuous charging window
        
        sim_pcm = simulate_pcm_tes_24h(df_24h, tes_trh, charge_chiller_tr, fleet_installed_tr=peak_tr)
        pcm_capex = calc_capex_breakup(scope, "PCM TES", peak_tr, tes_trh, charge_chiller_tr, rates)["total_capex"]
        pcm_opex = sim_pcm["annual_opex"]
        
        opex_savings = base_opex - pcm_opex
        capex_delta = pcm_capex if scope == "Brownfield (Retrofit)" else (pcm_capex - base_capex)
        payback, roi = calc_payback_and_roi(capex_delta, opex_savings)
        
        if payback <= 4.0 and opex_savings > best_pcm_savings:
            best_pcm_savings = opex_savings
            best_pcm = {
                "tes_trh": tes_trh,
                "charge_chiller_tr": charge_chiller_tr,
                "sim": sim_pcm,
                "capex": pcm_capex,
                "opex": pcm_opex,
                "opex_savings": opex_savings,
                "payback_years": payback,
                "roi_pct": roi,
                "num_tanks": int(np.ceil(tes_trh / 25000.0))
            }
            
    if best_pcm is None:
        tes_trh = 3017.0
        charge_chiller_tr = 378.0
        sim_pcm = simulate_pcm_tes_24h(df_24h, tes_trh, charge_chiller_tr, fleet_installed_tr=peak_tr)
        pcm_capex = calc_capex_breakup(scope, "PCM TES", peak_tr, tes_trh, charge_chiller_tr, rates)["total_capex"]
        pcm_opex = sim_pcm["annual_opex"]
        opex_savings = base_opex - pcm_opex
        payback, roi = calc_payback_and_roi(pcm_capex if scope == "Brownfield (Retrofit)" else (pcm_capex - base_capex), opex_savings)
        best_pcm = {
            "tes_trh": tes_trh,
            "charge_chiller_tr": charge_chiller_tr,
            "sim": sim_pcm,
            "capex": pcm_capex,
            "opex": pcm_opex,
            "opex_savings": opex_savings,
            "payback_years": payback,
            "roi_pct": roi,
            "num_tanks": 1
        }

    # 2. Stratified TES Optimization Search
    best_strat = None
    best_strat_savings = -1e9
    
    for tes_trh in test_capacities:
        sim_strat = simulate_stratified_tes_24h(df_24h, tes_trh, fleet_installed_tr=peak_tr)
        strat_capex = calc_capex_breakup(scope, "Stratified TES", peak_tr, tes_trh, 0, rates)["total_capex"]
        strat_opex = sim_strat["annual_opex"]
        
        opex_savings = base_opex - strat_opex
        capex_delta = strat_capex if scope == "Brownfield (Retrofit)" else (strat_capex - base_capex)
        payback, roi = calc_payback_and_roi(capex_delta, opex_savings)
        
        if payback <= 4.0 and opex_savings > best_strat_savings:
            best_strat_savings = opex_savings
            best_strat = {
                "tes_trh": tes_trh,
                "charge_chiller_tr": 0.0,
                "sim": sim_strat,
                "capex": strat_capex,
                "opex": strat_opex,
                "opex_savings": opex_savings,
                "payback_years": payback,
                "roi_pct": roi,
                "num_tanks": int(np.ceil(tes_trh / 25000.0))
            }
            
    if best_strat is None:
        tes_trh = 2901.0
        sim_strat = simulate_stratified_tes_24h(df_24h, tes_trh, fleet_installed_tr=peak_tr)
        strat_capex = calc_capex_breakup(scope, "Stratified TES", peak_tr, tes_trh, 0, rates)["total_capex"]
        strat_opex = sim_strat["annual_opex"]
        opex_savings = base_opex - strat_opex
        payback, roi = calc_payback_and_roi(strat_capex if scope == "Brownfield (Retrofit)" else (strat_capex - base_capex), opex_savings)
        best_strat = {
            "tes_trh": tes_trh,
            "charge_chiller_tr": 0.0,
            "sim": sim_strat,
            "capex": strat_capex,
            "opex": strat_opex,
            "opex_savings": opex_savings,
            "payback_years": payback,
            "roi_pct": roi,
            "num_tanks": 1
        }

    return {
        "baseline": {
            "capex": base_capex,
            "opex": base_opex,
            "sim": base_sim
        },
        "pcm": best_pcm,
        "stratified": best_strat
    }