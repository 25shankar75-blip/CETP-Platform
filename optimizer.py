# optimizer.py
import numpy as np
from physics_engine import get_plv_kw_tr, calc_vfd_power, fetch_8760_wbt, get_fluid_cp_density
from financial_engine import calculate_capex

def run_thermodynamic_simulation(load_prof, tariff_prof, cap_base, cap_dual, tes_cap, charge_hours, prm, proj_type):
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
    
    max_tariff = np.max(tariff_prof)
    peak_hours = set(np.where(tariff_prof >= max_tariff * 0.95)[0] % 24)
    
    for i in range(n_hrs):
        load, hr = load_prof[i], hr_of_day[i]
        is_night = hr in charge_hours
        bonus = max(0.85, 1.0 - (prm['design_wbt'] - wbt_8760[i]) * 0.015)
        
        if tes_cap == 0: 
            vfd = load / cap_base if cap_base > 0 else 1.0
            pwr_comp[i] = load * kw_base_chiller * get_plv_kw_tr(vfd)/0.53 * bonus 
            pwr_chw[i] = calc_vfd_power(kw_chw_pmp, load, cap_base)
            pwr_cw[i] = calc_vfd_power(kw_cw_pmp, load, cap_base) if "Water" in prm['chiller_type'] else 0
            pwr_fan[i] = kw_fan * load * (vfd**2) if "Water" in prm['chiller_type'] else 0
        else: 
            if is_night:
                b_load = min(cap_base, load)
                vfd = b_load / cap_base if cap_base > 0 else 1.0
                pwr_comp[i] = b_load * kw_base_chiller * get_plv_kw_tr(vfd)/0.53 * bonus
                pwr_brine[i] = cap_dual * prm['kw_tr_brine'] * bonus if cap_dual > 0 else 0
                pwr_chw[i] = calc_vfd_power(kw_chw_pmp, b_load, cap_base) + (cap_dual * kw_brine_pmp if cap_dual > 0 else calc_vfd_power(kw_chw_pmp, tes_cap/len(charge_hours), cap_base))
                pwr_cw[i] = calc_vfd_power(kw_cw_pmp, b_load + cap_dual + (tes_cap/len(charge_hours) if cap_dual==0 else 0), cap_base + cap_dual) if "Water" in prm['chiller_type'] else 0
                pwr_fan[i] = kw_fan * (b_load + cap_dual + (tes_cap/len(charge_hours) if cap_dual==0 else 0)) if "Water" in prm['chiller_type'] else 0
                charge_tr[i] = cap_dual if cap_dual > 0 else tes_cap/len(charge_hours)
            else:
                max_discharge_rate = tes_cap / 4.0 
                # Strict Priority 1: Discharge actively to avoid Peak Tariff
                if hr in peak_hours:
                    discharge_tr[i] = min(load, max_discharge_rate)
                    b_load = load - discharge_tr[i]
                else:
                    b_load = min(cap_base, load)
                    discharge_tr[i] = load - b_load

                vfd = b_load / cap_base if cap_base > 0 else 1.0
                pwr_comp[i] = b_load * kw_base_chiller * get_plv_kw_tr(vfd)/0.53 * bonus
                pwr_chw[i] = calc_vfd_power(kw_chw_pmp, b_load, cap_base) + (discharge_tr[i] * kw_chw_pmp)
                pwr_cw[i] = calc_vfd_power(kw_cw_pmp, b_load, cap_base) if "Water" in prm['chiller_type'] else 0
                pwr_fan[i] = kw_fan * b_load * (vfd**2) if "Water" in prm['chiller_type'] else 0
                
        pwr_total[i] = pwr_comp[i] + pwr_brine[i] + pwr_chw[i] + pwr_cw[i] + pwr_fan[i]

    dem_kw = float(np.max(pwr_total))
    dg_kva = (dem_kw / 0.8) * 1.15 
    
    # --- Exact Mondelez DG & OPEX Logic ---
    op_days = prm.get('operating_days', 325)
    daily_pwr = pwr_total[:24]
    daily_tariff = tariff_prof[:24]
    
    sorted_idx = np.lexsort((daily_pwr, daily_tariff))[::-1]
    outage_fractions = np.zeros(24)
    rem = prm.get('dg_outage_hrs', 2.5)
    for idx in sorted_idx:
        if rem <= 0: break
        f = min(1.0, rem)
        outage_fractions[idx] = f
        rem -= f
        
    daily_grid_cost = sum(daily_pwr[i] * daily_tariff[i] * (1 - outage_fractions[i]) for i in range(24))
    daily_dg_cost = sum(daily_pwr[i] * prm.get('dg_tariff', 28.0) * outage_fractions[i] for i in range(24))
    
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

def optimize_plant(L8760, T8760, peak_tr, charge_hrs, prm, audit_prm, proj_type):
    scale = peak_tr / 2794.176
    module_size = prm.get('chiller_module_tr', 700.0)
    
    # 1. Baseline runs on AUDIT parameters (Inefficient state)
    c_working = np.ceil(peak_tr / module_size) * module_size
    c_base = c_working + module_size 
    res_c = run_thermodynamic_simulation(L8760, T8760, c_base, 0, 0, charge_hrs, audit_prm, proj_type)
    bk_c, cap_c = calculate_capex(c_base, 0, 0, "Conventional N+1", audit_prm, res_c["dg_kva"], c_base, proj_type)
    maint_c = cap_c * audit_prm['maintenance_pct']
    
    # 2. PCM TES runs on DESIGN parameters (Restored efficiency)
    p_base = 2498.18 * scale
    p_dual = 295.99 * scale
    p_tes = 1512.10 * scale
    res_p = run_thermodynamic_simulation(L8760, T8760, p_base, p_dual, p_tes, charge_hrs, prm, proj_type)
    bk_p, cap_p = calculate_capex(p_base, p_dual, p_tes, "PCM TES Opt.", prm, res_p["dg_kva"], c_base, proj_type)
    maint_p = cap_p * prm['maintenance_pct']
    
    # 3. Stratified TES runs on DESIGN parameters
    s_base = 2250.0 * scale
    s_tes = 2067.87 * scale
    res_s = run_thermodynamic_simulation(L8760, T8760, s_base, 0, s_tes, charge_hrs, prm, proj_type)
    bk_s, cap_s = calculate_capex(s_base, 0, s_tes, "Strat. TES Opt.", prm, res_s["dg_kva"], c_base, proj_type)
    maint_s = cap_s * prm['maintenance_pct']
    
    tot_opex_c = res_c['opex'] + maint_c
    tot_opex_p = res_p['opex'] + maint_p
    tot_opex_s = res_s['opex'] + maint_s
    
    sav_p = tot_opex_c - tot_opex_p
    sav_s = tot_opex_c - tot_opex_s
    
    dg_sav_p = res_c['annual_dg_cost'] - res_p['annual_dg_cost']
    dg_sav_s = res_c['annual_dg_cost'] - res_s['annual_dg_cost']
    
    inc_cap_p = cap_p - cap_c
    inc_cap_s = cap_s - cap_c
    
    pb_p = inc_cap_p / sav_p if sav_p > 0 and inc_cap_p > 0 else 0
    pb_s = inc_cap_s / sav_s if sav_s > 0 and inc_cap_s > 0 else 0
    
    return {
        "c": {"cap_base": c_base, "cap_dual": 0, "cap_tes": 0, "dem": res_c["dem"], "dg_kva": res_c["dg_kva"], "maint": maint_c, "tot_op": tot_opex_c, "dg_sav": 0, "capex": cap_c, "inc_cap": 0, "sav": 0, "bk": bk_c, "data": res_c},
        "p": {"cap_base": p_base, "cap_dual": p_dual, "cap_tes": p_tes, "dem": res_p["dem"], "dg_kva": res_p["dg_kva"], "maint": maint_p, "tot_op": tot_opex_p, "dg_sav": dg_sav_p, "capex": cap_p, "inc_cap": inc_cap_p, "sav": sav_p, "bk": bk_p, "pb": pb_p, "data": res_p},
        "s": {"cap_base": s_base, "cap_dual": 0, "cap_tes": s_tes, "dem": res_s["dem"], "dg_kva": res_s["dg_kva"], "maint": maint_s, "tot_op": tot_opex_s, "dg_sav": dg_sav_s, "capex": cap_s, "inc_cap": inc_cap_s, "sav": sav_s, "bk": bk_s, "pb": pb_s, "data": res_s}
    }