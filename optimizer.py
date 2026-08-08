"""
Cooling Energy Transition Platform (CETP) - Iterative Optimizer
File: optimizer.py
"""
import numpy as np
from physics_engine import simulate_conventional, simulate_pcm, simulate_stratified, check_fleet_air_cooled

def build_capex_breakdown(sys_type, scope, fleet_tr, tes_trh, charge_chiller_tr, rates, is_air_cooled=False):
    """Generates precise equipment CAPEX line items, honoring Sunk Costs for Retrofits."""
    b = {
        "Chiller Equip.": 0.0, "TES Tank": 0.0, "PCM Media": 0.0, "Pumps & PHE": 0.0, 
        "Electrical": 0.0, "Water Infra": 0.0, "Transformer": 0.0, "DG Set": 0.0
    }
    
    if sys_type == "Conventional":
        if scope == "Brownfield (Retrofit)": 
            return {"Total CAPEX": 0.0, "Breakdown": b}  # SUNK COST BASELINE LOCK
        c_rate = rates.get("ac_chiller_rate", 24000.0) if is_air_cooled else rates.get("base_chiller_rate", 22000.0)
        b["Chiller Equip."] = fleet_tr * c_rate
        b["Pumps & PHE"] = 0.0 if is_air_cooled else fleet_tr * 2500.0
        b["Electrical"] = fleet_tr * 1500.0
        b["Water Infra"] = 0.0 if is_air_cooled else fleet_tr * rates.get("water_infra_rate", 1200.0)
        b["Transformer"] = fleet_tr * 0.8 * rates.get("transformer_rate", 3500.0)
        b["DG Set"] = fleet_tr * 0.8 * rates.get("dg_set_rate", 12500.0)
        
    elif sys_type == "PCM":
        b["Chiller Equip."] = charge_chiller_tr * rates.get("brine_chiller_rate", 25000.0)
        b["TES Tank"] = tes_trh * 2800.0
        b["PCM Media"] = tes_trh * 4500.0
        b["Pumps & PHE"] = charge_chiller_tr * 3000.0
        b["Electrical"] = charge_chiller_tr * 1500.0
        b["Water Infra"] = 0.0 if is_air_cooled else charge_chiller_tr * rates.get("water_infra_rate", 1200.0)
        b["Transformer"] = charge_chiller_tr * 0.8 * rates.get("transformer_rate", 3500.0)
        b["DG Set"] = charge_chiller_tr * 0.8 * rates.get("dg_set_rate", 12500.0)
        
    elif sys_type == "Stratified":
        b["TES Tank"] = tes_trh * rates.get("stratified_tes_rate", 18000.0) * 0.75
        b["Pumps & PHE"] = (tes_trh / 8.0) * 1500.0
        b["Electrical"] = (tes_trh / 8.0) * 1000.0
        b["Water Infra"] = 0.0 if is_air_cooled else (tes_trh / 8.0) * rates.get("water_infra_rate", 1200.0)

    subtotal = sum(b.values())
    indirects = subtotal * rates.get("indirects_pct", 0.30)
    b["Indirects / AMC"] = indirects
    return {"Total CAPEX": subtotal + indirects, "Breakdown": b}

def eval_payback(capex_delta, opex_savings):
    if opex_savings <= 0: return 99.9
    return capex_delta / opex_savings

def optimize_plant(df_comp, load_arr, tar_arr, wbt_arr, proj_scope, audit_cfg, rates, running_days):
    """
    EOS-01 Compliant Optimizer: Evaluates 8760-hr OPEX dispatch before sizing hardware.
    Iterates through storage capacities to find the global maximum OPEX savings limit < 4yr payback.
    """
    fleet_tr = sum(df_comp["Capacity (TR)"] * df_comp["Quantity"]) if not df_comp.empty else max(load_arr) * 1.2
    is_ac = check_fleet_air_cooled(df_comp)
    
    # 1. Baseline Simulation (Captures Audit Inefficiencies if Retrofit)
    sim_conv = simulate_conventional(load_arr, tar_arr, wbt_arr, fleet_tr, proj_scope, audit_cfg, df_comp, running_days)
    cap_conv = build_capex_breakdown("Conventional", proj_scope, fleet_tr, 0, 0, rates, is_ac)
    
    water_cost_conv = sim_conv["water_m3"] * audit_cfg.get("water_cost_per_m3", 65.0)
    sim_conv["annual_opex"] += water_cost_conv
    
    # Global Optimum Search Space
    search_space = np.linspace(500, max(load_arr)*12, 25)
    
    # 2. Encapsulated PCM Optimization Loop
    best_pcm = {"opex_savings": -1, "payback": 99}
    for trh in search_space:
        c_tr = trh / 8.0  # 8-Hour strict charge window
        sim = simulate_pcm(load_arr, tar_arr, wbt_arr, fleet_tr, trh, c_tr, df_comp, running_days)
        cap = build_capex_breakdown("PCM", proj_scope, fleet_tr, trh, c_tr, rates, is_ac)
        
        w_cost = sim["water_m3"] * audit_cfg.get("water_cost_per_m3", 65.0)
        sim["annual_opex"] += w_cost
        
        sav = sim_conv["annual_opex"] - sim["annual_opex"]
        delta_c = cap["Total CAPEX"] if proj_scope == "Brownfield (Retrofit)" else (cap["Total CAPEX"] - cap_conv["Total CAPEX"])
        pb = eval_payback(delta_c, sav)
        
        if pb <= 4.0 and sav > best_pcm["opex_savings"]:
            best_pcm = {
                "tes_trh": trh, "chiller_tr": c_tr, "sim": sim, "cap": cap, 
                "opex_savings": sav, "payback": pb, "num_tanks": int(np.ceil(trh / 25000.0)), "water_cost": w_cost
            }
            
    if best_pcm["opex_savings"] == -1: # Fallback constraints
        trh, c_tr = 3017.0, 378.0
        sim = simulate_pcm(load_arr, tar_arr, wbt_arr, fleet_tr, trh, c_tr, df_comp, running_days)
        cap = build_capex_breakdown("PCM", proj_scope, fleet_tr, trh, c_tr, rates, is_ac)
        w_cost = sim["water_m3"] * audit_cfg.get("water_cost_per_m3", 65.0)
        sim["annual_opex"] += w_cost
        sav = sim_conv["annual_opex"] - sim["annual_opex"]
        delta_c = cap["Total CAPEX"] if proj_scope == "Brownfield (Retrofit)" else (cap["Total CAPEX"] - cap_conv["Total CAPEX"])
        best_pcm = {"tes_trh": trh, "chiller_tr": c_tr, "sim": sim, "cap": cap, "opex_savings": sav, "payback": eval_payback(delta_c, sav), "num_tanks": 1, "water_cost": w_cost}

    # 3. Stratified Chilled Water Optimization Loop
    best_strat = {"opex_savings": -1, "payback": 99}
    for trh in search_space:
        sim = simulate_stratified(load_arr, tar_arr, wbt_arr, fleet_tr, trh, df_comp, running_days)
        cap = build_capex_breakdown("Stratified", proj_scope, fleet_tr, trh, 0, rates, is_ac)
        
        w_cost = sim["water_m3"] * audit_cfg.get("water_cost_per_m3", 65.0)
        sim["annual_opex"] += w_cost
        
        sav = sim_conv["annual_opex"] - sim["annual_opex"]
        delta_c = cap["Total CAPEX"] if proj_scope == "Brownfield (Retrofit)" else (cap["Total CAPEX"] - cap_conv["Total CAPEX"])
        pb = eval_payback(delta_c, sav)
        
        if pb <= 4.0 and sav > best_strat["opex_savings"]:
            best_strat = {
                "tes_trh": trh, "sim": sim, "cap": cap, "opex_savings": sav, 
                "payback": pb, "num_tanks": int(np.ceil(trh / 25000.0)), "water_cost": w_cost
            }
            
    if best_strat["opex_savings"] == -1: # Fallback constraints
        trh = 2900.0
        sim = simulate_stratified(load_arr, tar_arr, wbt_arr, fleet_tr, trh, df_comp, running_days)
        cap = build_capex_breakdown("Stratified", proj_scope, fleet_tr, trh, 0, rates, is_ac)
        w_cost = sim["water_m3"] * audit_cfg.get("water_cost_per_m3", 65.0)
        sim["annual_opex"] += w_cost
        sav = sim_conv["annual_opex"] - sim["annual_opex"]
        delta_c = cap["Total CAPEX"] if proj_scope == "Brownfield (Retrofit)" else (cap["Total CAPEX"] - cap_conv["Total CAPEX"])
        best_strat = {"tes_trh": trh, "sim": sim, "cap": cap, "opex_savings": sav, "payback": eval_payback(delta_c, sav), "num_tanks": 1, "water_cost": w_cost}

    # 4. Integrate DG Outage Diesel Penalties & Grid Offset
    dg_cost_baseline = rates.get("dg_diesel_cost_kwh", 24.50) * (np.mean(sim_conv["comp_kw"]) + np.mean(sim_conv["chw_pri_kw"]) + np.mean(sim_conv["chw_sec_kw"])) * rates.get("daily_outage_hrs", 1.5) * running_days
    
    # TES shifts major loads during outages, running only secondary pumps on DG
    dg_cost_tes_p = rates.get("dg_diesel_cost_kwh", 24.50) * (np.mean(best_pcm["sim"]["chw_sec_kw"])) * rates.get("daily_outage_hrs", 1.5) * running_days
    dg_cost_tes_s = rates.get("dg_diesel_cost_kwh", 24.50) * (np.mean(best_strat["sim"]["chw_sec_kw"])) * rates.get("daily_outage_hrs", 1.5) * running_days
    
    avg_tariff = np.mean(tar_arr)
    grid_offset_p = (dg_cost_baseline - dg_cost_tes_p) * (avg_tariff / rates.get("dg_diesel_cost_kwh", 24.50)) if proj_scope == "Brownfield (Retrofit)" else 0.0
    grid_offset_s = (dg_cost_baseline - dg_cost_tes_s) * (avg_tariff / rates.get("dg_diesel_cost_kwh", 24.50)) if proj_scope == "Brownfield (Retrofit)" else 0.0

    sim_conv["annual_opex"] += dg_cost_baseline
    best_pcm["sim"]["annual_opex"] += dg_cost_tes_p
    best_strat["sim"]["annual_opex"] += dg_cost_tes_s
    
    best_pcm["opex_savings"] = sim_conv["annual_opex"] - best_pcm["sim"]["annual_opex"]
    best_strat["opex_savings"] = sim_conv["annual_opex"] - best_strat["sim"]["annual_opex"]
    
    best_pcm["payback"] = eval_payback(best_pcm["cap"]["Total CAPEX"] if proj_scope == "Brownfield (Retrofit)" else (best_pcm["cap"]["Total CAPEX"] - cap_conv["Total CAPEX"]), best_pcm["opex_savings"])
    best_strat["payback"] = eval_payback(best_strat["cap"]["Total CAPEX"] if proj_scope == "Brownfield (Retrofit)" else (best_strat["cap"]["Total CAPEX"] - cap_conv["Total CAPEX"]), best_strat["opex_savings"])

    # CO2 Emission Reduction (Grid Emission Factor: 0.82 kg CO2 / kWh)
    co2_saved_p = ((sim_conv["annual_opex"] - best_pcm["sim"]["annual_opex"]) / max(1.0, avg_tariff)) * 0.82 / 1000.0
    co2_saved_s = ((sim_conv["annual_opex"] - best_strat["sim"]["annual_opex"]) / max(1.0, avg_tariff)) * 0.82 / 1000.0

    return {
        "c": {"capex": cap_conv["Total CAPEX"], "opex": sim_conv["annual_opex"], "bk": cap_conv["Breakdown"], "sim": sim_conv, "dg_cost": dg_cost_baseline, "water_cost": water_cost_conv, "co2": 0.0},
        "p": {"tes_trh": best_pcm["tes_trh"], "chiller_tr": best_pcm["chiller_tr"], "num_tanks": best_pcm["num_tanks"], "capex": best_pcm["cap"]["Total CAPEX"], "opex": best_pcm["sim"]["annual_opex"], "bk": best_pcm["cap"]["Breakdown"], "sim": best_pcm["sim"], "pb": best_pcm["payback"], "sav": best_pcm["opex_savings"], "dg_cost": dg_cost_tes_p, "water_cost": best_pcm["water_cost"], "grid_offset": grid_offset_p, "co2": co2_saved_p},
        "s": {"tes_trh": best_strat["tes_trh"], "num_tanks": best_strat["num_tanks"], "capex": best_strat["cap"]["Total CAPEX"], "opex": best_strat["sim"]["annual_opex"], "bk": best_strat["cap"]["Breakdown"], "sim": best_strat["sim"], "pb": best_strat["payback"], "sav": best_strat["opex_savings"], "dg_cost": dg_cost_tes_s, "water_cost": best_strat["water_cost"], "grid_offset": grid_offset_s, "co2": co2_saved_s}
    }