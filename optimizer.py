import numpy as np
from physics_engine import get_plv_kw_tr, calc_vfd_power, fetch_8760_wbt
from financial_engine import calculate_capex

def run_thermodynamic_simulation(load_prof, tariff_prof, cap_base, cap_dual, tes_cap, tes_type, prm, proj_type):
    n_hrs = len(load_prof)
    hr_of_day = np.arange(n_hrs) % 24
    wbt_8760 = fetch_8760_wbt(prm['location'], prm['design_wbt'], prm['use_live_weather'])
    
    pwr_comp, pwr_brine, pwr_chw, pwr_cw, pwr_fan, pwr_total = np.zeros(n_hrs), np.zeros(n_hrs), np.zeros(n_hrs), np.zeros(n_hrs), np.zeros(n_hrs), np.zeros(n_hrs)
    charge_tr, discharge_tr = np.zeros(n_hrs), np.zeros(n_hrs)
    
    kw_chw_pmp = prm['chw_pump_kw']
    kw_cw_pmp = prm['cw_pump_kw']
    kw_fan = prm['ct_fan_kw']
    kw_brine_pmp = prm['brine_pump_kw']
    kw_base_chiller = prm['kw_tr_base']
    
    # Sort daily tariffs to isolate cheapest charge windows and peak discharge windows
    daily_tariff = tariff_prof[:24]
    cheapest_hrs = np.argsort(daily_tariff)
    expensive_hrs = np.argsort(daily_tariff)[::-1]
    
    charge_window = set(cheapest_hrs[:8])
    discharge_window = set(expensive_hrs[:10])
    
    for i in range(n_hrs):
        load, hr = load_prof[i], hr_of_day[i]
        bonus = max(0.85, 1.0 - (prm['design_wbt'] - wbt_8760[i]) * 0.015)
        
        if tes_cap == 0: 
            vfd = load / cap_base if cap_base > 0 else 1.0
            pwr_comp[i] = load * kw_base_chiller * get_plv_kw_tr(vfd)/0.53 * bonus 
            pwr_chw[i] = calc_vfd_power(kw_chw_pmp, load, cap_base)
            pwr_cw[i] = calc_vfd_power(kw_cw_pmp, load, cap_base) if "Water" in prm['chiller_type'] else 0
            pwr_fan[i] = kw_fan * load * (vfd**2) if "Water" in prm['chiller_type'] else 0
        else:
            # Dispatch Logic 
            is_charging = hr in charge_window
            is_discharging = hr in discharge_window
            
            b_load = load
            active_charge = 0.0
            active_discharge = 0.0
            
            # Discharge Phase (High Tariff)
            if is_discharging:
                max_discharge_rate = tes_cap / 4.0
                active_discharge = min(load, max_discharge_rate)
                b_load = load - active_discharge
                discharge_tr[i] = active_discharge
            
            # Charge Phase (Low Tariff)
            if is_charging:
                if tes_type == "PCM":
                    active_charge = cap_dual 
                    charge_tr[i] = active_charge
                    pwr_brine[i] = active_charge * prm['kw_tr_brine'] * bonus
                    pwr_chw[i] += active_charge * kw_brine_pmp
                    pwr_cw[i] += calc_vfd_power(kw_cw_pmp, active_charge, cap_dual) if "Water" in prm['chiller_type'] else 0
                    pwr_fan[i] += kw_fan * active_charge if "Water" in prm['chiller_type'] else 0
                elif tes_type == "STRAT":
                    spare_capacity = max(0, cap_base - b_load)
                    active_charge = min(spare_capacity, tes_cap / 6.0)
                    charge_tr[i] = active_charge
                    b_load += active_charge
            
            # Base Chiller Operations (Satisfying remaining load + Stratified Charge)
            b_load = min(b_load, cap_base)
            vfd = b_load / cap_base if cap_base > 0 else 1.0
            pwr_comp[i] = b_load * kw_base_chiller * get_plv_kw_tr(vfd)/0.53 * bonus
            pwr_chw[i] += calc_vfd_power(kw_chw_pmp, b_load, cap_base) + (active_discharge * kw_chw_pmp)
            pwr_cw[i] += calc_vfd_power(kw_cw_pmp, b_load, cap_base) if "Water" in prm['chiller_type'] else 0
            pwr_fan[i] += kw_fan * b_load * (vfd**2) if "Water" in prm['chiller_type'] else 0
                
        pwr_total[i] = pwr_comp[i] + pwr_brine[i] + pwr_chw[i] + pwr_cw[i] + pwr_fan[i]

    dem_kw = float(np.max(pwr_total))
    dg_kva = (dem_kw / 0.8) * 1.15 
    
    # Mondelez DG Penalty & OPEX Logic
    op_days = prm.get('operating_days', 325)
    daily_pwr = pwr_total[:24]
    
    outage_fractions = np.zeros(24)
    rem = prm.get('dg_outage_hrs', 2.5)
    for idx in expensive_hrs:
        if rem <= 0: break
        f = min(1.0, rem)
        outage_fractions[idx] = f
        rem -= f
        
    daily_grid_cost = sum(daily_pwr[j] * daily_tariff[j] * (1 - outage_fractions[j]) for j in range(24))
    daily_dg_cost = sum(daily_pwr[j] * prm.get('dg_tariff', 28.0) * outage_fractions[j] for j in range(24))
    
    energy_kwh = sum(daily_pwr) * op_days
    annual_grid_cost = daily_grid_cost * op_days
    annual_dg_cost = daily_dg_cost * op_days
    energy_cost = annual_grid_cost + annual_dg_cost
    
    water_kl = (np.sum(load_prof[:24]) * prm['evap_loss']) / 1000.0 * op_days if "Water" in prm['chiller_type'] else 0.0
    water_cost = water_kl * prm['water_cost_kl']
    
    opex = energy_cost + (dg_kva * prm['demand_rate'] * 12) + water_cost
    emissions_tons = (energy_kwh * prm['grid_emission']) / 1000.0
    
    annual_breakdown = {
        "Base Chiller": {"kwh": np.sum(pwr_comp[:24]) * op_days, "cost": np.sum(pwr_comp[:24] * daily_tariff) * op_days},
        "Brine Chiller": {"kwh": np.sum(pwr_brine[:24]) * op_days, "cost": np.sum(pwr_brine[:24] * daily_tariff) * op_days},
        "CHW Pumps": {"kwh": np.sum(pwr_chw[:24]) * op_days, "cost": np.sum(pwr_chw[:24] * daily_tariff) * op_days},
        "CW Pumps": {"kwh": np.sum(pwr_cw[:24]) * op_days, "cost": np.sum(pwr_cw[:24] * daily_tariff) * op_days},
        "CT Fans": {"kwh": np.sum(pwr_fan[:24]) * op_days, "cost": np.sum(pwr_fan[:24] * daily_tariff) * op_days}
    }
    
    return {
        "kw_comp": pwr_comp, "kw_brine": pwr_brine, "kw_chw": pwr_chw, "kw_cw": pwr_cw, "kw_fan": pwr_fan, "total_kw": pwr_total, "tariff": tariff_prof,
        "charge": charge_tr, "discharge": discharge_tr, "dem": dem_kw, "dg_kva": dg_kva, "energy_kwh": energy_kwh, "energy_cost": energy_cost, 
        "opex": opex, "emissions": emissions_tons, "water_kl": water_kl, "water_cost": water_cost, "annual_dg_cost": annual_dg_cost, "breakdown": annual_breakdown
    }

def optimize_plant(L8760, T8760, installed_chiller_tr, prm, audit_prm, proj_type):
    is_retro = "Brownfield" in proj_type
    
    # 1. BASELINE (AUDIT parameters for Inefficient state)
    c_base = installed_chiller_tr if installed_chiller_tr > 0 else max(L8760[:24]) * 1.15
    
    res_c = run_thermodynamic_simulation(L8760, T8760, c_base, 0, 0, "NONE", audit_prm, proj_type)
    bk_c, cap_c, mech_cap_c = calculate_capex(c_base, 0, 0, "Conventional N+1", audit_prm, res_c["dg_kva"], c_base, proj_type)
    maint_c = mech_cap_c * audit_prm['maintenance_pct'] 
    tot_opex_c = res_c['opex'] + maint_c
    
    # Iterative Permutation Engine: Test sizes from 10% to 150% of Total Daily Load
    daily_load_trh = sum(L8760[:24])
    tes_sizes = np.linspace(max(500, daily_load_trh * 0.1), daily_load_trh * 1.5, 10)
    
    best_p, best_s = None, None
    max_sav_p, max_sav_s = -1e12, -1e12
    fallback_p, fallback_s = None, None
    
    # Stratified Retrofit Bottleneck: Available off-peak capacity of existing chillers
    daily_tariff = T8760[:24]
    cheapest_hrs = np.argsort(daily_tariff)[:8]
    available_charge_cap = sum(max(0, c_base - L8760[h]) for h in cheapest_hrs)
    
    for t_cap in tes_sizes:
        # --- PCM PERMUTATION (Add New Brine Chiller) ---
        p_dual = t_cap / 8.0 
        p_base = c_base if is_retro else max(0, installed_chiller_tr - p_dual)
            
        res_p_tmp = run_thermodynamic_simulation(L8760, T8760, p_base, p_dual, t_cap, "PCM", prm, proj_type)
        bk_p_tmp, cap_p_tmp, mech_cap_p_tmp = calculate_capex(p_base, p_dual, t_cap, "PCM TES Opt.", prm, res_p_tmp["dg_kva"], c_base, proj_type)
        maint_p_tmp = mech_cap_p_tmp * prm['maintenance_pct'] 
        tot_opex_p_tmp = res_p_tmp['opex'] + maint_p_tmp
        
        sav_p = tot_opex_c - tot_opex_p_tmp
        inc_cap_p = cap_p_tmp - cap_c
        pb_p = inc_cap_p / sav_p if sav_p > 0 else 999
        
        if fallback_p is None or pb_p < fallback_p[10]: 
            fallback_p = (p_base, p_dual, t_cap, res_p_tmp, bk_p_tmp, cap_p_tmp, maint_p_tmp, tot_opex_p_tmp, sav_p, inc_cap_p, pb_p)
            
        if pb_p <= 4.0 and sav_p > max_sav_p: # < 4 year ROI Threshold
            max_sav_p = sav_p
            best_p = (p_base, p_dual, t_cap, res_p_tmp, bk_p_tmp, cap_p_tmp, maint_p_tmp, tot_opex_p_tmp, sav_p, inc_cap_p, pb_p)
            
        # --- STRATIFIED PERMUTATION (Use Existing Chillers) ---
        s_t_cap = min(t_cap, available_charge_cap) if is_retro else t_cap
        s_dual = 0
        s_base = c_base if is_retro else max(0, installed_chiller_tr - (s_t_cap/4.0))
            
        res_s_tmp = run_thermodynamic_simulation(L8760, T8760, s_base, s_dual, s_t_cap, "STRAT", prm, proj_type)
        bk_s_tmp, cap_s_tmp, mech_cap_s_tmp = calculate_capex(s_base, s_dual, s_t_cap, "Strat. TES Opt.", prm, res_s_tmp["dg_kva"], c_base, proj_type)
        maint_s_tmp = mech_cap_s_tmp * prm['maintenance_pct'] 
        tot_opex_s_tmp = res_s_tmp['opex'] + maint_s_tmp
        
        sav_s = tot_opex_c - tot_opex_s_tmp
        inc_cap_s = cap_s_tmp - cap_c
        pb_s = inc_cap_s / sav_s if sav_s > 0 else 999
        
        if fallback_s is None or pb_s < fallback_s[10]:
            fallback_s = (s_base, s_dual, s_t_cap, res_s_tmp, bk_s_tmp, cap_s_tmp, maint_s_tmp, tot_opex_s_tmp, sav_s, inc_cap_s, pb_s)
        
        if pb_s <= 4.0 and sav_s > max_sav_s:
            max_sav_s = sav_s
            best_s = (s_base, s_dual, s_t_cap, res_s_tmp, bk_s_tmp, cap_s_tmp, maint_s_tmp, tot_opex_s_tmp, sav_s, inc_cap_s, pb_s)

    best_p = best_p if best_p is not None else fallback_p
    best_s = best_s if best_s is not None else fallback_s
    
    return {
        "c": {"cap_base": c_base, "cap_dual": 0, "cap_tes": 0, "dem": res_c["dem"], "dg_kva": res_c["dg_kva"], "maint": maint_c, "tot_op": tot_opex_c, "dg_sav": 0, "capex": cap_c, "inc_cap": 0, "sav": 0, "bk": bk_c, "data": res_c},
        "p": {"cap_base": best_p[0], "cap_dual": best_p[1], "cap_tes": best_p[2], "dem": best_p[3]["dem"], "dg_kva": best_p[3]["dg_kva"], "maint": best_p[6], "tot_op": best_p[7], "dg_sav": res_c['annual_dg_cost'] - best_p[3]['annual_dg_cost'], "capex": best_p[5], "inc_cap": best_p[9], "sav": best_p[8], "bk": best_p[4], "pb": best_p[10], "data": best_p[3]},
        "s": {"cap_base": best_s[0], "cap_dual": best_s[1], "cap_tes": best_s[2], "dem": best_s[3]["dem"], "dg_kva": best_s[3]["dg_kva"], "maint": best_s[6], "tot_op": best_s[7], "dg_sav": res_c['annual_dg_cost'] - best_s[3]['annual_dg_cost'], "capex": best_s[5], "inc_cap": best_s[9], "sav": best_s[8], "bk": best_s[4], "pb": best_s[10], "data": best_s[3]}
    }