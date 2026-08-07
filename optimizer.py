"""
Cooling Energy Transition Platform (CETP) - Iterative Optimizer
File: optimizer.py
"""
import numpy as np
from physics_engine import simulate_conventional, simulate_pcm, simulate_stratified

def build_capex_breakdown(sys_type, scope, fleet_tr, tes_trh, charge_chiller_tr, rates):
    b = {"Chiller Equip.": 0, "TES Tank": 0, "PCM Media": 0, "Pumps & PHE": 0, "Electrical": 0}
    if sys_type == "Conventional":
        if scope == "Brownfield (Retrofit)": return {"Total CAPEX": 0.0, "Breakdown": b} # Sunk Cost
        b["Chiller Equip."] = fleet_tr * rates["base_chiller_rate"]
        b["Pumps & PHE"] = fleet_tr * 2500
        b["Electrical"] = fleet_tr * 1500
    elif sys_type == "PCM":
        b["Chiller Equip."] = charge_chiller_tr * rates["brine_chiller_rate"]
        b["TES Tank"] = tes_trh * 2800
        b["PCM Media"] = tes_trh * 4500
        b["Pumps & PHE"] = charge_chiller_tr * 3000
        b["Electrical"] = charge_chiller_tr * 1500
    elif sys_type == "Stratified":
        b["TES Tank"] = tes_trh * rates["stratified_tes_rate"] * 0.75
        b["Pumps & PHE"] = (tes_trh/8) * 1500
        b["Electrical"] = (tes_trh/8) * 1000

    subtotal = sum(b.values())
    return {"Total CAPEX": subtotal * (1.0 + rates["indirects_pct"]), "Breakdown": b}

def eval_payback(capex_delta, opex_savings):
    if opex_savings <= 0: return 99.9
    return capex_delta / opex_savings

def optimize_plant(df_comp, load_arr, tar_arr, proj_scope, audit_cfg, rates):
    fleet_tr = sum(df_comp["Capacity (TR)"] * df_comp["Quantity"]) if not df_comp.empty else max(load_arr) * 1.2
    
    # 1. Baseline Simulation (Captures Audit Inefficiencies if Brownfield)
    sim_conv = simulate_conventional(load_arr, tar_arr, fleet_tr, proj_scope, audit_cfg)
    cap_conv = build_capex_breakdown("Conventional", proj_scope, fleet_tr, 0, 0, rates)
    
    search_space = np.linspace(500, max(load_arr)*12, 30)
    
    # 2. PCM Optimization
    best_pcm = {"opex_savings": -1, "payback": 99}
    for trh in search_space:
        c_tr = trh / 8.0 
        sim = simulate_pcm(load_arr, tar_arr, fleet_tr, trh, c_tr)
        cap = build_capex_breakdown("PCM", proj_scope, fleet_tr, trh, c_tr, rates)
        
        sav = sim_conv["annual_opex"] - sim["annual_opex"]
        delta_c = cap["Total CAPEX"] if proj_scope == "Brownfield (Retrofit)" else (cap["Total CAPEX"] - cap_conv["Total CAPEX"])
        pb = eval_payback(delta_c, sav)
        
        if pb <= 4.0 and sav > best_pcm["opex_savings"]:
            best_pcm = {"tes_trh": trh, "chiller_tr": c_tr, "sim": sim, "cap": cap, "opex_savings": sav, "payback": pb}
            
    if best_pcm["opex_savings"] == -1: # Fallback
        trh, c_tr = 3017.0, 378.0
        sim = simulate_pcm(load_arr, tar_arr, fleet_tr, trh, c_tr)
        cap = build_capex_breakdown("PCM", proj_scope, fleet_tr, trh, c_tr, rates)
        best_pcm = {"tes_trh": trh, "chiller_tr": c_tr, "sim": sim, "cap": cap, "opex_savings": sim_conv["annual_opex"] - sim["annual_opex"], "payback": eval_payback(cap["Total CAPEX"] if proj_scope == "Brownfield (Retrofit)" else cap["Total CAPEX"] - cap_conv["Total CAPEX"], sim_conv["annual_opex"] - sim["annual_opex"])}

    # 3. Stratified Optimization
    best_strat = {"opex_savings": -1, "payback": 99}
    for trh in search_space:
        sim = simulate_stratified(load_arr, tar_arr, fleet_tr, trh)
        cap = build_capex_breakdown("Stratified", proj_scope, fleet_tr, trh, 0, rates)
        
        sav = sim_conv["annual_opex"] - sim["annual_opex"]
        delta_c = cap["Total CAPEX"] if proj_scope == "Brownfield (Retrofit)" else (cap["Total CAPEX"] - cap_conv["Total CAPEX"])
        pb = eval_payback(delta_c, sav)
        
        if pb <= 4.0 and sav > best_strat["opex_savings"]:
            best_strat = {"tes_trh": trh, "sim": sim, "cap": cap, "opex_savings": sav, "payback": pb}
            
    if best_strat["opex_savings"] == -1: # Fallback
        trh = 2900.0
        sim = simulate_stratified(load_arr, tar_arr, fleet_tr, trh)
        cap = build_capex_breakdown("Stratified", proj_scope, fleet_tr, trh, 0, rates)
        best_strat = {"tes_trh": trh, "sim": sim, "cap": cap, "opex_savings": sim_conv["annual_opex"] - sim["annual_opex"], "payback": eval_payback(cap["Total CAPEX"] if proj_scope == "Brownfield (Retrofit)" else cap["Total CAPEX"] - cap_conv["Total CAPEX"], sim_conv["annual_opex"] - sim["annual_opex"])}

    return {
        "c": {"capex": cap_conv["Total CAPEX"], "opex": sim_conv["annual_opex"], "bk": cap_conv["Breakdown"], "sim": sim_conv},
        "p": {"tes_trh": best_pcm["tes_trh"], "chiller_tr": best_pcm["chiller_tr"], "capex": best_pcm["cap"]["Total CAPEX"], "opex": best_pcm["sim"]["annual_opex"], "bk": best_pcm["cap"]["Breakdown"], "sim": best_pcm["sim"], "pb": best_pcm["payback"], "sav": best_pcm["opex_savings"]},
        "s": {"tes_trh": best_strat["tes_trh"], "capex": best_strat["cap"]["Total CAPEX"], "opex": best_strat["sim"]["annual_opex"], "bk": best_strat["cap"]["Breakdown"], "sim": best_strat["sim"], "pb": best_strat["payback"], "sav": best_strat["opex_savings"]}
    }