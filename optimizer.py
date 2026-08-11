"""
Cooling Energy Transition Platform (CETP) - Iterative Optimizer
File: optimizer.py
"""
import numpy as np
from physics_engine import simulate_conventional, simulate_pcm, simulate_stratified, check_fleet_air_cooled

def build_capex_breakdown(sys_type, scope, active_tr, tes_trh, extra_chiller_tr, rates, is_air_cooled=False, tank_shape="Cylindrical Tank"):
    """Generates precise equipment CAPEX line items, guaranteeing 9 keys."""
    b = {
        "Chiller Equip.": 0.0, 
        "TES Tank": 0.0, 
        "PCM Media": 0.0, 
        "Pumps & PHE": 0.0, 
        "Electrical": 0.0, 
        "Water Infra": 0.0, 
        "Transformer": 0.0, 
        "DG Set": 0.0,
        "Indirects / AMC": 0.0  
    }
    
    is_greenfield = scope != "Brownfield (Retrofit)"
    
    if sys_type == "Conventional":
        if not is_greenfield: 
            return {"Total CAPEX": 0.0, "Breakdown": b}  
            
        c_rate = rates.get("ac_chiller_rate", 24000.0) if is_air_cooled else rates.get("base_chiller_rate", 22000.0)
        b["Chiller Equip."] = active_tr * c_rate
        b["Pumps & PHE"] = 0.0 if is_air_cooled else active_tr * 2500.0
        b["Electrical"] = active_tr * 1500.0
        b["Water Infra"] = 0.0 if is_air_cooled else active_tr * rates.get("water_infra_rate", 1200.0)
        b["Transformer"] = active_tr * 0.8 * rates.get("transformer_rate", 3500.0)
        b["DG Set"] = active_tr * 0.8 * rates.get("dg_set_rate", 12500.0)
        
    elif sys_type == "PCM":
        b["Chiller Equip."] = extra_chiller_tr * rates.get("brine_chiller_rate", 25000.0)
        if is_greenfield:
            b["Chiller Equip."] += active_tr * (rates.get("ac_chiller_rate", 24000.0) if is_air_cooled else rates.get("base_chiller_rate", 22000.0))
        
        pcm_rate = rates.get("pcm_cyl_rate", 7800.0) if tank_shape == "Cylindrical Tank" else rates.get("pcm_rect_rate", 8300.0)
        b["TES Tank"] = tes_trh * pcm_rate 
        
        cap_tr = (active_tr + extra_chiller_tr) if is_greenfield else extra_chiller_tr
        b["Pumps & PHE"] = cap_tr * 3000.0
        b["Electrical"] = cap_tr * 1500.0
        b["Water Infra"] = 0.0 if is_air_cooled else cap_tr * rates.get("water_infra_rate", 1200.0)
        b["Transformer"] = cap_tr * 0.8 * rates.get("transformer_rate", 3500.0)
        b["DG Set"] = cap_tr * 0.8 * rates.get("dg_set_rate", 12500.0)
        
    elif sys_type == "Stratified":
        if is_greenfield:
            b["Chiller Equip."] = active_tr * (rates.get("ac_chiller_rate", 24000.0) if is_air_cooled else rates.get("base_chiller_rate", 22000.0))
            
        b["TES Tank"] = tes_trh * rates.get("stratified_tes_rate", 18000.0)
        
        cap_tr = (active_tr + (tes_trh / 8.0)) if is_greenfield else (tes_trh / 8.0)
        b["Pumps & PHE"] = cap_tr * 1500.0
        b["Electrical"] = cap_tr * 1000.0
        b["Water Infra"] = 0.0 if is_air_cooled else cap_tr * rates.get("water_infra_rate", 1200.0)
        b["Transformer"] = cap_tr * 0.8 * rates.get("transformer_rate", 3500.0)
        b["DG Set"] = cap_tr * 0.8 * rates.get("dg_set_rate", 12500.0)

    subtotal = sum(v for k, v in b.items() if k != "Indirects / AMC")
    indirects = subtotal * rates.get("indirects_pct", 0.30)
    b["Indirects / AMC"] = indirects
    
    return {"Total CAPEX": subtotal + indirects, "Breakdown": b}

def eval_payback(capex_delta, opex_savings):
    if opex_savings <= 0: return 99.9
    return capex_delta / opex_savings

def optimize_plant(df_comp, load_arr, tar_arr, wbt_arr, proj_scope, audit_cfg, rates, running_days, tank_shape):
    is_ac = check_fleet_air_cooled(df_comp)
    is_greenfield = proj_scope != "Brownfield (Retrofit)"
    peak_load = max(load_arr)
    
    total_installed_tr = sum(df_comp["Capacity (TR)"] * df_comp["Quantity"]) if not df_comp.empty else peak_load * 1.2
    active_df = df_comp[df_comp["Standby"] == False] if "Standby" in df_comp.columns else df_comp
    active_working_tr = sum(active_df["Capacity (TR)"] * active_df["Quantity"]) if not active_df.empty else total_installed_tr

    existing_brine_tr = 0.0
    if not is_greenfield and not df_comp.empty:
        brine_df = df_comp[df_comp["Chiller Type"].isin(["Sub-Zero Brine Chiller", "Dual-Mode Chiller"])]
        if not brine_df.empty: existing_brine_tr = sum(brine_df["Capacity (TR)"] * brine_df["Quantity"])
    
    # 1. Baseline Simulation
    sim_conv = simulate_conventional(load_arr, tar_arr, wbt_arr, active_working_tr, proj_scope, audit_cfg, df_comp, running_days)
    cap_conv = build_capex_breakdown("Conventional", proj_scope, total_installed_tr, 0, 0, rates, is_ac, tank_shape)
    water_cost_conv = sim_conv["water_m3"] * audit_cfg.get("water_cost_per_m3", 65.0)
    sim_conv["annual_opex"] += water_cost_conv
    
    # 2. Constraints & Search Spaces
    rolling_8_tar = [sum(tar_arr[(i+j)%24] for j in range(8)) for i in range(24)]
    charge_start_hr = np.argmin(rolling_8_tar)
    charge_hrs = [(charge_start_hr + j) % 24 for j in range(8)]
    avg_spare_capacity = np.mean([max(0, active_working_tr - load_arr[h]) for h in charge_hrs])

    if is_greenfield:
        pcm_search_space = np.linspace(peak_load * 0.5, peak_load * 8, 25)
        strat_search_space = np.linspace(peak_load * 0.5, peak_load * 4, 15) # Hard cap on Stratified sizing
    else:
        max_retrofit_trh = max(500, avg_spare_capacity * 8.0) # Strictly bounded by spare fleet capacity
        pcm_search_space = np.linspace(500, max_retrofit_trh, 20)
        strat_search_space = np.linspace(500, min(max_retrofit_trh, peak_load * 4), 15)
    
    # 3. PCM Optimization Loop
    best_pcm = {"opex_savings": -1, "payback": 99, "score": -9999}
    for trh in pcm_search_space:
        c_tr = trh / 8.0  
        new_c_tr = max(0.0, c_tr - existing_brine_tr) if not is_greenfield else c_tr
        base_chiller_tr = max(peak_load * 0.4, peak_load - (trh / 10.0)) if is_greenfield else active_working_tr
        
        sim = simulate_pcm(load_arr, tar_arr, wbt_arr, base_chiller_tr, trh, c_tr, df_comp, audit_cfg, running_days, proj_scope)
        cap = build_capex_breakdown("PCM", proj_scope, base_chiller_tr, trh, new_c_tr, rates, is_ac, tank_shape)
        
        w_cost = sim["water_m3"] * audit_cfg.get("water_cost_per_m3", 65.0)
        sim["annual_opex"] += w_cost
        
        sav = sim_conv["annual_opex"] - sim["annual_opex"]
        delta_c = cap["Total CAPEX"] if not is_greenfield else (cap["Total CAPEX"] - cap_conv["Total CAPEX"])
        pb = eval_payback(delta_c, sav)
        
        if pb <= 4.5 and sav > 0:
            score = sav / max(0.1, pb) if is_greenfield else sav # Greenfield prioritizes CAPEX efficiency; Retrofit prioritizes OPEX Arbitrage
            if score > best_pcm["score"]:
                best_pcm = {"tes_trh": trh, "chiller_tr": c_tr, "new_chiller_tr": new_c_tr, "base_chiller_tr": base_chiller_tr, "sim": sim, "cap": cap, "opex_savings": sav, "payback": pb, "score": score, "num_tanks": int(np.ceil(trh / 25000.0)), "water_cost": w_cost}
            
    if best_pcm["opex_savings"] == -1: 
        trh = pcm_search_space[len(pcm_search_space)//2]
        c_tr = trh / 8.0
        new_c_tr = max(0.0, c_tr - existing_brine_tr) if not is_greenfield else c_tr
        base_chiller_tr = max(peak_load * 0.4, peak_load - (trh / 10.0)) if is_greenfield else active_working_tr
        sim = simulate_pcm(load_arr, tar_arr, wbt_arr, base_chiller_tr, trh, c_tr, df_comp, audit_cfg, running_days, proj_scope)
        cap = build_capex_breakdown("PCM", proj_scope, base_chiller_tr, trh, new_c_tr, rates, is_ac, tank_shape)
        w_cost = sim["water_m3"] * audit_cfg.get("water_cost_per_m3", 65.0)
        sim["annual_opex"] += w_cost
        sav = sim_conv["annual_opex"] - sim["annual_opex"]
        delta_c = cap["Total CAPEX"] if not is_greenfield else (cap["Total CAPEX"] - cap_conv["Total CAPEX"])
        best_pcm = {"tes_trh": trh, "chiller_tr": c_tr, "new_chiller_tr": new_c_tr, "base_chiller_tr": base_chiller_tr, "sim": sim, "cap": cap, "opex_savings": sav, "payback": eval_payback(delta_c, sav), "score": 0, "num_tanks": 1, "water_cost": w_cost}

    # 4. Stratified Chilled Water Optimization Loop
    best_strat = {"opex_savings": -1, "payback": 99, "score": -9999}
    for trh in strat_search_space:
        base_chiller_tr = max(peak_load * 0.5, peak_load - (trh / 8.0)) if is_greenfield else active_working_tr
        
        sim = simulate_stratified(load_arr, tar_arr, wbt_arr, base_chiller_tr, trh, df_comp, audit_cfg, running_days, proj_scope)
        cap = build_capex_breakdown("Stratified", proj_scope, base_chiller_tr, trh, 0, rates, is_ac, tank_shape)
        
        w_cost = sim["water_m3"] * audit_cfg.get("water_cost_per_m3", 65.0)
        sim["annual_opex"] += w_cost
        
        sav = sim_conv["annual_opex"] - sim["annual_opex"]
        delta_c = cap["Total CAPEX"] if not is_greenfield else (cap["Total CAPEX"] - cap_conv["Total CAPEX"])
        pb = eval_payback(delta_c, sav)
        
        if pb <= 4.5 and sav > 0:
            score = sav / max(0.1, pb) if is_greenfield else sav
            if score > best_strat["score"]:
                best_strat = {"tes_trh": trh, "base_chiller_tr": base_chiller_tr, "sim": sim, "cap": cap, "opex_savings": sav, "payback": pb, "score": score, "num_tanks": int(np.ceil(trh / 25000.0)), "water_cost": w_cost}
            
    if best_strat["opex_savings"] == -1: 
        trh = strat_search_space[len(strat_search_space)//2]
        base_chiller_tr = max(peak_load * 0.5, peak_load - (trh / 8.0)) if is_greenfield else active_working_tr
        sim = simulate_stratified(load_arr, tar_arr, wbt_arr, base_chiller_tr, trh, df_comp, audit_cfg, running_days, proj_scope)
        cap = build_capex_breakdown("Stratified", proj_scope, base_chiller_tr, trh, 0, rates, is_ac, tank_shape)
        w_cost = sim["water_m3"] * audit_cfg.get("water_cost_per_m3", 65.0)
        sim["annual_opex"] += w_cost
        sav = sim_conv["annual_opex"] - sim["annual_opex"]
        delta_c = cap["Total CAPEX"] if not is_greenfield else (cap["Total CAPEX"] - cap_conv["Total CAPEX"])
        best_strat = {"tes_trh": trh, "base_chiller_tr": base_chiller_tr, "sim": sim, "cap": cap, "opex_savings": sav, "payback": eval_payback(delta_c, sav), "score": 0, "num_tanks": 1, "water_cost": w_cost}

    # 5. Outage Penalties & Final Structuring
    dg_cost_baseline = rates.get("dg_diesel_cost_kwh", 24.50) * (np.mean(sim_conv["comp_kw"]) + np.mean(sim_conv["chw_pri_kw"]) + np.mean(sim_conv["chw_sec_kw"])) * rates.get("daily_outage_hrs", 1.5) * running_days
    dg_cost_tes_p = rates.get("dg_diesel_cost_kwh", 24.50) * (np.mean(best_pcm["sim"]["chw_sec_kw"])) * rates.get("daily_outage_hrs", 1.5) * running_days
    dg_cost_tes_s = rates.get("dg_diesel_cost_kwh", 24.50) * (np.mean(best_strat["sim"]["chw_sec_kw"])) * rates.get("daily_outage_hrs", 1.5) * running_days
    
    avg_tariff = np.mean(tar_arr)
    grid_offset_p = (dg_cost_baseline - dg_cost_tes_p) * (avg_tariff / rates.get("dg_diesel_cost_kwh", 24.50)) if not is_greenfield else 0.0
    grid_offset_s = (dg_cost_baseline - dg_cost_tes_s) * (avg_tariff / rates.get("dg_diesel_cost_kwh", 24.50)) if not is_greenfield else 0.0

    sim_conv["annual_opex"] += dg_cost_baseline
    best_pcm["sim"]["annual_opex"] += dg_cost_tes_p
    best_strat["sim"]["annual_opex"] += dg_cost_tes_s
    
    best_pcm["opex_savings"] = sim_conv["annual_opex"] - best_pcm["sim"]["annual_opex"]
    best_strat["opex_savings"] = sim_conv["annual_opex"] - best_strat["sim"]["annual_opex"]
    
    best_pcm["payback"] = eval_payback(best_pcm["cap"]["Total CAPEX"] if not is_greenfield else (best_pcm["cap"]["Total CAPEX"] - cap_conv["Total CAPEX"]), best_pcm["opex_savings"])
    best_strat["payback"] = eval_payback(best_strat["cap"]["Total CAPEX"] if not is_greenfield else (best_strat["cap"]["Total CAPEX"] - cap_conv["Total CAPEX"]), best_strat["opex_savings"])

    co2_saved_p = ((sim_conv["annual_opex"] - best_pcm["sim"]["annual_opex"]) / max(1.0, avg_tariff)) * 0.82 / 1000.0
    co2_saved_s = ((sim_conv["annual_opex"] - best_strat["sim"]["annual_opex"]) / max(1.0, avg_tariff)) * 0.82 / 1000.0

    return {
        "c": {"base_chiller_tr": total_installed_tr if is_greenfield else active_working_tr, "capex": cap_conv["Total CAPEX"], "opex": sim_conv["annual_opex"], "bk": cap_conv["Breakdown"], "sim": sim_conv, "dg_cost": dg_cost_baseline, "water_cost": water_cost_conv, "co2": 0.0},
        "p": {"tes_trh": best_pcm["tes_trh"], "chiller_tr": best_pcm["chiller_tr"], "new_chiller_tr": best_pcm["new_chiller_tr"], "base_chiller_tr": best_pcm["base_chiller_tr"], "num_tanks": best_pcm["num_tanks"], "capex": best_pcm["cap"]["Total CAPEX"], "opex": best_pcm["sim"]["annual_opex"], "bk": best_pcm["cap"]["Breakdown"], "sim": best_pcm["sim"], "pb": best_pcm["payback"], "sav": best_pcm["opex_savings"], "dg_cost": dg_cost_tes_p, "water_cost": best_pcm["water_cost"], "grid_offset": grid_offset_p, "co2": co2_saved_p},
        "s": {"tes_trh": best_strat["tes_trh"], "base_chiller_tr": best_strat["base_chiller_tr"], "num_tanks": best_strat["num_tanks"], "capex": best_strat["cap"]["Total CAPEX"], "opex": best_strat["sim"]["annual_opex"], "bk": best_strat["cap"]["Breakdown"], "sim": best_strat["sim"], "pb": best_strat["payback"], "sav": best_strat["opex_savings"], "dg_cost": dg_cost_tes_s, "water_cost": best_strat["water_cost"], "grid_offset": grid_offset_s, "co2": co2_saved_s}
    }