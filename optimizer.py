"""
Cooling Energy Transition Platform (CETP) - Iterative Optimizer
File: optimizer.py
"""
import numpy as np
from physics_engine import simulate_conventional, simulate_pcm, simulate_stratified, check_fleet_air_cooled

def build_capex_breakdown(sys_type, scope, base_tr, tes_trh, brine_tr, rates, is_air_cooled=False, tank_shape="Cylindrical Tank"):
    """Strict 8-Key CAPEX Array"""
    b = {
        "Chiller Equip.": 0.0, 
        "TES System": 0.0, 
        "Pumps & PHE": 0.0, 
        "Electrical": 0.0, 
        "Water Infra": 0.0, 
        "Transformer": 0.0, 
        "DG Set": 0.0,
        "Indirects / AMC": 0.0  
    }
    
    is_greenfield = scope != "Brownfield (Retrofit)"
    
    # Fallbacks for empty rates
    base_rate = rates.get("base_chiller_rate") or 22000.0
    ac_rate = rates.get("ac_chiller_rate") or 24000.0
    brine_rate = rates.get("brine_chiller_rate") or 25000.0
    water_rate = rates.get("water_infra_rate") or 1200.0
    trans_rate = rates.get("transformer_rate") or 3500.0
    dg_rate = rates.get("dg_set_rate") or 12500.0
    pcm_cyl = rates.get("pcm_cyl_rate") or 7800.0
    pcm_rect = rates.get("pcm_rect_rate") or 8300.0
    strat_rate = rates.get("stratified_tes_rate") or 18000.0
    indirect_pct = rates.get("indirects_pct") or 0.30

    if sys_type == "Conventional":
        if not is_greenfield: return {"Total CAPEX": 0.0, "Breakdown": b}  
        c_rate = ac_rate if is_air_cooled else base_rate
        b["Chiller Equip."] = base_tr * c_rate
        b["Pumps & PHE"] = 0.0 if is_air_cooled else base_tr * 2500.0
        b["Electrical"] = base_tr * 1500.0
        b["Water Infra"] = 0.0 if is_air_cooled else base_tr * water_rate
        b["Transformer"] = base_tr * 0.8 * trans_rate
        b["DG Set"] = base_tr * 0.8 * dg_rate
        
    elif sys_type == "PCM":
        b["Chiller Equip."] = brine_tr * brine_rate
        if is_greenfield: b["Chiller Equip."] += base_tr * (ac_rate if is_air_cooled else base_rate)
        
        pcm_rate = pcm_cyl if tank_shape == "Cylindrical Tank" else pcm_rect
        b["TES System"] = tes_trh * pcm_rate 
        
        cap_tr = (base_tr + brine_tr) if is_greenfield else brine_tr
        b["Pumps & PHE"] = cap_tr * 3000.0
        b["Electrical"] = cap_tr * 1500.0
        b["Water Infra"] = 0.0 if is_air_cooled else cap_tr * water_rate
        b["Transformer"] = cap_tr * 0.8 * trans_rate
        b["DG Set"] = cap_tr * 0.8 * dg_rate
        
    elif sys_type == "Stratified":
        if is_greenfield: b["Chiller Equip."] = base_tr * (ac_rate if is_air_cooled else base_rate)
        b["TES System"] = tes_trh * strat_rate
        
        cap_tr = (base_tr + (tes_trh / 8.0)) if is_greenfield else (tes_trh / 8.0)
        b["Pumps & PHE"] = cap_tr * 1500.0
        b["Electrical"] = cap_tr * 1000.0
        b["Water Infra"] = 0.0 if is_air_cooled else cap_tr * water_rate
        b["Transformer"] = cap_tr * 0.8 * trans_rate
        b["DG Set"] = cap_tr * 0.8 * dg_rate

    subtotal = sum(v for k, v in b.items() if k != "Indirects / AMC")
    b["Indirects / AMC"] = subtotal * indirect_pct
    
    return {"Total CAPEX": subtotal + b["Indirects / AMC"], "Breakdown": b}

def eval_payback(capex_delta, opex_savings):
    if opex_savings <= 0: return 99.9
    return capex_delta / opex_savings

def optimize_plant(df_comp, load_arr, tar_arr, wbt_arr, proj_scope, audit_cfg, rates, running_days, tank_shape):
    is_ac = check_fleet_air_cooled(df_comp)
    is_greenfield = proj_scope != "Brownfield (Retrofit)"
    peak_load = max(load_arr)
    
    total_installed_tr = sum(df_comp["Capacity (TR)"] * df_comp["Quantity"]) if not df_comp.empty else peak_load * 1.2
    active_df = df_comp[df_comp["Standby"] == False] if "Standby" in df_comp.columns else df_comp
    active_working_tr = max(1.0, sum(active_df["Capacity (TR)"] * active_df["Quantity"]) if not active_df.empty else total_installed_tr)

    existing_brine_tr = 0.0
    if not is_greenfield and not df_comp.empty:
        brine_df = df_comp[df_comp["Chiller Type"].isin(["Sub-Zero Brine Chiller", "Dual-Mode Chiller"])]
        if not brine_df.empty: existing_brine_tr = sum(brine_df["Capacity (TR)"] * brine_df["Quantity"])
    
    # Baseline
    sim_conv = simulate_conventional(load_arr, tar_arr, wbt_arr, active_working_tr, proj_scope, audit_cfg, df_comp, running_days)
    cap_conv = build_capex_breakdown("Conventional", proj_scope, total_installed_tr, 0, 0, rates, is_ac, tank_shape)
    water_cost_conv = sim_conv["water_m3"] * (audit_cfg.get("water_cost_per_m3") or 65.0)
    sim_conv["annual_opex"] += water_cost_conv
    
    rolling_8_tar = [sum(tar_arr[(i+j)%24] for j in range(8)) for i in range(24)]
    charge_hrs = [(np.argmin(rolling_8_tar) + j) % 24 for j in range(8)]
    avg_spare_capacity = np.mean([max(0.0, active_working_tr - load_arr[h]) for h in charge_hrs])

    if is_greenfield:
        pcm_search_space = np.linspace(peak_load * 1.0, peak_load * 8, 25)
        strat_search_space = np.linspace(peak_load * 1.0, peak_load * 4, 15)
    else:
        max_retrofit_trh = max(500.0, avg_spare_capacity * 8.0) 
        pcm_search_space = np.linspace(500, max_retrofit_trh, 20)
        strat_search_space = np.linspace(500, min(max_retrofit_trh, peak_load * 4), 15)
    
    # Helper to evaluate config
    def evaluate_tes(trh, is_pcm):
        sim = simulate_pcm(load_arr, tar_arr, wbt_arr, active_working_tr, trh, df_comp, audit_cfg, running_days, proj_scope) if is_pcm else simulate_stratified(load_arr, tar_arr, wbt_arr, active_working_tr, trh, df_comp, audit_cfg, running_days, proj_scope)
        base_chiller_tr = sim["base_chiller_tr"]
        c_tr = sim["charge_chiller_tr"]
        new_c_tr = max(0.0, c_tr - existing_brine_tr) if not is_greenfield else c_tr
        cap = build_capex_breakdown("PCM" if is_pcm else "Stratified", proj_scope, base_chiller_tr, trh, new_c_tr if is_pcm else 0, rates, is_ac, tank_shape)
        w_cost = sim["water_m3"] * (audit_cfg.get("water_cost_per_m3") or 65.0)
        sim["annual_opex"] += w_cost
        sav = sim_conv["annual_opex"] - sim["annual_opex"]
        delta_c = cap["Total CAPEX"] if not is_greenfield else (cap["Total CAPEX"] - cap_conv["Total CAPEX"])
        pb = eval_payback(delta_c, sav)
        
        # Strict Rejection Criteria (< 4.0 ROI and CAPEX validation)
        status = "NOT RECOMMENDED"
        if pb <= 4.0 and sav > 0:
            if not is_greenfield or (is_greenfield and cap["Total CAPEX"] <= cap_conv["Total CAPEX"]):
                status = "RECOMMENDED"

        return {"tes_trh": trh, "chiller_tr": c_tr, "new_chiller_tr": new_c_tr, "base_chiller_tr": base_chiller_tr, "sim": sim, "cap": cap, "opex_savings": sav, "payback": pb, "score": sav / max(0.1, pb) if is_greenfield else sav, "num_tanks": int(np.ceil(trh / 25000.0)), "water_cost": w_cost, "status": status}

    # Optimization Loops
    best_pcm = {"status": "NOT RECOMMENDED", "score": -9999}
    for trh in pcm_search_space:
        res = evaluate_tes(trh, is_pcm=True)
        if res["status"] == "RECOMMENDED" and res["score"] > best_pcm.get("score", -9999): best_pcm = res
    if best_pcm["status"] == "NOT RECOMMENDED": best_pcm = evaluate_tes(pcm_search_space[len(pcm_search_space)//2], True)

    best_strat = {"status": "NOT RECOMMENDED", "score": -9999}
    for trh in strat_search_space:
        res = evaluate_tes(trh, is_pcm=False)
        if res["status"] == "RECOMMENDED" and res["score"] > best_strat.get("score", -9999): best_strat = res
    if best_strat["status"] == "NOT RECOMMENDED": best_strat = evaluate_tes(strat_search_space[len(strat_search_space)//2], False)

    # Outages & DG Offsets
    dg_kwh_cost = rates.get("dg_diesel_cost_kwh") or 24.50
    outage_hrs = rates.get("daily_outage_hrs") or 1.5
    
    dg_cost_baseline = dg_kwh_cost * (np.mean(sim_conv["comp_kw"]) + np.mean(sim_conv["chw_pri_kw"]) + np.mean(sim_conv["chw_sec_kw"])) * outage_hrs * running_days
    avg_tariff = np.mean(tar_arr)

    for best_cfg in [best_pcm, best_strat]:
        dg_cost_tes = dg_kwh_cost * (np.mean(best_cfg["sim"]["chw_sec_kw"])) * outage_hrs * running_days
        grid_offset = (dg_cost_baseline - dg_cost_tes) * (avg_tariff / dg_kwh_cost) if not is_greenfield else 0.0
        best_cfg["sim"]["annual_opex"] += dg_cost_tes
        best_cfg["opex_savings"] = sim_conv["annual_opex"] + dg_cost_baseline - best_cfg["sim"]["annual_opex"]
        delta_c = best_cfg["cap"]["Total CAPEX"] if not is_greenfield else (best_cfg["cap"]["Total CAPEX"] - cap_conv["Total CAPEX"])
        best_cfg["payback"] = eval_payback(delta_c, best_cfg["opex_savings"])
        best_cfg["co2"] = (best_cfg["opex_savings"] / max(1.0, avg_tariff)) * 0.82 / 1000.0
        best_cfg["dg_cost"] = dg_cost_tes
        best_cfg["grid_offset"] = grid_offset
        if best_cfg["payback"] > 4.0: best_cfg["status"] = "NOT RECOMMENDED"

    sim_conv["annual_opex"] += dg_cost_baseline

    return {
        "c": {"base_chiller_tr": total_installed_tr if is_greenfield else active_working_tr, "capex": cap_conv["Total CAPEX"], "opex": sim_conv["annual_opex"], "bk": cap_conv["Breakdown"], "sim": sim_conv, "dg_cost": dg_cost_baseline, "water_cost": water_cost_conv, "co2": 0.0, "status": "BASELINE"},
        "p": best_pcm,
        "s": best_strat
    }