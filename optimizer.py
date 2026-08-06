"""
CETP Digital Twin - Iterative Plant Optimizer
File: optimizer.py
"""
import numpy as np
import pandas as pd
from physics_engine import simulate_conventional, simulate_pcm, simulate_stratified
from financial_engine import build_capex_breakdown, eval_payback

def optimize_plant(df_comp, load_arr, tar_arr, proj_scope, rates):
    fleet_tr = sum(df_comp["Capacity (TR)"] * df_comp["Quantity"]) if not df_comp.empty else max(load_arr) * 1.2
    
    # 1. Evaluate Baseline
    sim_conv = simulate_conventional(load_arr, tar_arr, fleet_tr)
    cap_conv = build_capex_breakdown("Conventional", proj_scope, fleet_tr, 0, 0, rates)
    
    # 2. Iterative Search Space
    search_space = np.linspace(500, max(load_arr)*12, 30)
    
    best_pcm = {"opex_savings": -1, "payback": 99}
    for trh in search_space:
        c_tr = trh / 8.0 # 8 Hour charge
        sim = simulate_pcm(load_arr, tar_arr, fleet_tr, trh, c_tr)
        cap = build_capex_breakdown("PCM", proj_scope, fleet_tr, trh, c_tr, rates)
        
        sav = sim_conv["annual_opex"] - sim["annual_opex"]
        delta_c = cap["Total CAPEX"] if proj_scope == "Brownfield (Retrofit)" else (cap["Total CAPEX"] - cap_conv["Total CAPEX"])
        pb = eval_payback(delta_c, sav)
        
        if pb <= 4.0 and sav > best_pcm["opex_savings"]:
            best_pcm = {"tes_trh": trh, "chiller_tr": c_tr, "sim": sim, "cap": cap, "opex_savings": sav, "payback": pb}
            
    # Fallback if no <4 yr found
    if best_pcm["opex_savings"] == -1:
        trh, c_tr = 3017.0, 378.0
        sim = simulate_pcm(load_arr, tar_arr, fleet_tr, trh, c_tr)
        cap = build_capex_breakdown("PCM", proj_scope, fleet_tr, trh, c_tr, rates)
        best_pcm = {"tes_trh": trh, "chiller_tr": c_tr, "sim": sim, "cap": cap, "opex_savings": sim_conv["annual_opex"] - sim["annual_opex"], "payback": eval_payback(cap["Total CAPEX"], sim_conv["annual_opex"] - sim["annual_opex"])}

    best_strat = {"opex_savings": -1, "payback": 99}
    for trh in search_space:
        sim = simulate_stratified(load_arr, tar_arr, fleet_tr, trh)
        cap = build_capex_breakdown("Stratified", proj_scope, fleet_tr, trh, 0, rates)
        
        sav = sim_conv["annual_opex"] - sim["annual_opex"]
        delta_c = cap["Total CAPEX"] if proj_scope == "Brownfield (Retrofit)" else (cap["Total CAPEX"] - cap_conv["Total CAPEX"])
        pb = eval_payback(delta_c, sav)
        
        if pb <= 4.0 and sav > best_strat["opex_savings"]:
            best_strat = {"tes_trh": trh, "sim": sim, "cap": cap, "opex_savings": sav, "payback": pb}
            
    if best_strat["opex_savings"] == -1:
        trh = 2900.0
        sim = simulate_stratified(load_arr, tar_arr, fleet_tr, trh)
        cap = build_capex_breakdown("Stratified", proj_scope, fleet_tr, trh, 0, rates)
        best_strat = {"tes_trh": trh, "sim": sim, "cap": cap, "opex_savings": sim_conv["annual_opex"] - sim["annual_opex"], "payback": eval_payback(cap["Total CAPEX"], sim_conv["annual_opex"] - sim["annual_opex"])}

    return {
        "c": {"capex": cap_conv["Total CAPEX"], "opex": sim_conv["annual_opex"], "bk": cap_conv["Breakdown"], "sim": sim_conv},
        "p": {"tes_trh": best_pcm["tes_trh"], "chiller_tr": best_pcm["chiller_tr"], "capex": best_pcm["cap"]["Total CAPEX"], "opex": best_pcm["sim"]["annual_opex"], "bk": best_pcm["cap"]["Breakdown"], "sim": best_pcm["sim"], "pb": best_pcm["payback"], "sav": best_pcm["opex_savings"]},
        "s": {"tes_trh": best_strat["tes_trh"], "capex": best_strat["cap"]["Total CAPEX"], "opex": best_strat["sim"]["annual_opex"], "bk": best_strat["cap"]["Breakdown"], "sim": best_strat["sim"], "pb": best_strat["payback"], "sav": best_strat["opex_savings"]}
    }