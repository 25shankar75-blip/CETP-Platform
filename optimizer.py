# optimizer.py
import numpy as np
from physics_engine import get_plv_kw_tr, get_night_condenser_bonus, calc_vfd_power
from financial_engine import calculate_capex

def run_thermodynamic_simulation(load_prof, tariff_prof, cap_base, cap_dual, tes_cap, charge_hours, prm):
    n_hrs = len(load_prof)
    hr_of_day = np.arange(n_hrs) % 24
    
    pwr_comp, pwr_brine, pwr_chw, pwr_cw, pwr_fan, pwr_total = np.zeros(n_hrs), np.zeros(n_hrs), np.zeros(n_hrs), np.zeros(n_hrs), np.zeros(n_hrs), np.zeros(n_hrs)
    charge_tr, discharge_tr = np.zeros(n_hrs), np.zeros(n_hrs)
    
    kw_chw_pmp = prm['chw_pump_kw']
    kw_cw_pmp = prm['cw_pump_kw']
    kw_fan = prm['ct_fan_kw']
    kw_brine_pmp = prm['brine_pump_kw']
    
    for i in range(n_hrs):
        load, hr = load_prof[i], hr_of_day[i]
        is_night, bonus = hr in charge_hours, get_night_condenser_bonus(hr)
        
        if tes_cap == 0: # Conventional
            vfd = load / cap_base if cap_base > 0 else 1.0
            pwr_comp[i] = load * get_plv_kw_tr(vfd) * bonus
            pwr_chw[i] = calc_vfd_power(kw_chw_pmp, load, cap_base)
            pwr_cw[i] = calc_vfd_power(kw_cw_pmp, load, cap_base) if "Water" in prm['chiller_type'] else 0
            pwr_fan[i] = kw_fan * load * (vfd**2) if "Water" in prm['chiller_type'] else 0
        else: # PCM or Stratified TES
            if is_night:
                b_load = min(cap_base, load)
                vfd = b_load / cap_base if cap_base > 0 else 1.0
                pwr_comp[i] = b_load * get_plv_kw_tr(vfd) * bonus
                pwr_brine[i] = cap_dual * prm['kw_tr_brine'] * bonus if cap_dual > 0 else 0
                pwr_chw[i] = calc_vfd_power(kw_chw_pmp, b_load, cap_base) + (cap_dual * kw_brine_pmp if cap_dual > 0 else calc_vfd_power(kw_chw_pmp, tes_cap/len(charge_hours), cap_base))
                pwr_cw[i] = calc_vfd_power(kw_cw_pmp, b_load + cap_dual + (tes_cap/len(charge_hours) if cap_dual==0 else 0), cap_base + cap_dual) if "Water" in prm['chiller_type'] else 0
                pwr_fan[i] = kw_fan * (b_load + cap_dual + (tes_cap/len(charge_hours) if cap_dual==0 else 0)) if "Water" in prm['chiller_type'] else 0
                charge_tr[i] = cap_dual if cap_dual > 0 else tes_cap/len(charge_hours)
            else:
                b_load = cap_base if load > cap_base else load
                disch = load - cap_base if load > cap_base else 0
                vfd = b_load / cap_base if cap_base > 0 else 1.0
                pwr_comp[i] = b_load * get_plv_kw_tr(vfd) * bonus
                pwr_chw[i] = calc_vfd_power(kw_chw_pmp, b_load, cap_base) + (disch * kw_chw_pmp)
                pwr_cw[i] = calc_vfd_power(kw_cw_pmp, b_load, cap_base) if "Water" in prm['chiller_type'] else 0
                pwr_fan[i] = kw_fan * b_load * (vfd**2) if "Water" in prm['chiller_type'] else 0
                discharge_tr[i] = disch
                
        pwr_total[i] = pwr_comp[i] + pwr_brine[i] + pwr_chw[i] + pwr_cw[i] + pwr_fan[i]

    dem_kw = float(np.max(pwr_total))
    dg_kva = (dem_kw / 0.8) * 1.15 # 15% DG margin applied to Transformer rating
    energy_kwh = np.sum(pwr_total)
    water_kl = (np.sum(load_prof) * prm['evap_loss']) / 1000.0 if "Water" in prm['chiller_type'] else 0.0
    
    opex = np.sum(pwr_total * tariff_prof) + (dg_kva * prm['demand_rate'] * 12) + (water_kl * prm['water_cost_kl'])
    emissions_tons = (energy_kwh * prm['grid_emission']) / 1000.0
    
    return {
        "kw_comp": pwr_comp, "kw_brine": pwr_brine, "kw_chw": pwr_chw, "kw_cw": pwr_cw, "kw_fan": pwr_fan, "total_kw": pwr_total,
        "charge": charge_tr, "discharge": discharge_tr, "dem": dem_kw, "dg_kva": dg_kva, "opex": opex, "emissions": emissions_tons, "water_kl": water_kl
    }

def optimize_plant(L8760, T8760, peak_tr, charge_hrs, prm, proj_type):
    # Lock to EXACT Rev19 Load-Leveling methodology
    scale = peak_tr / 2794.176
    
    # 1. Conventional (Uses 700 TR Module Rounding matching Rev19 exactly)
    c_working = np.ceil(peak_tr / 700.0) * 700.0
    c_base = c_working + 700.0 # 4 Working + 1 Standby = 3500 TR for baseline
    res_c = run_thermodynamic_simulation(L8760, T8760, c_base, 0, 0, charge_hrs, prm)
    bk_c, cap_c = calculate_capex(c_base, 0, 0, "Conventional N+1", prm, res_c["dg_kva"], c_base, proj_type)
    
    # 2. PCM TES (Exact Chiller splits from Rev19)
    p_base = 2498.18 * scale
    p_dual = 295.99 * scale
    p_tes = 1512.10 * scale
    res_p = run_thermodynamic_simulation(L8760, T8760, p_base, p_dual, p_tes, charge_hrs, prm)
    bk_p, cap_p = calculate_capex(p_base, p_dual, p_tes, "PCM TES Opt.", prm, res_p["dg_kva"], c_base, proj_type)
    
    # 3. Stratified TES (Exact Chiller splits from Rev19)
    s_base = 2250.0 * scale
    s_tes = 2067.87 * scale
    res_s = run_thermodynamic_simulation(L8760, T8760, s_base, 0, s_tes, charge_hrs, prm)
    bk_s, cap_s = calculate_capex(s_base, 0, s_tes, "Strat. TES Opt.", prm, res_s["dg_kva"], c_base, proj_type)
    
    pb_p = (cap_p - cap_c) / (res_c['opex'] - res_p['opex']) if (res_c['opex'] - res_p['opex']) > 0 else 0
    pb_s = (cap_s - cap_c) / (res_c['opex'] - res_s['opex']) if (res_c['opex'] - res_s['opex']) > 0 else 0
    
    return {
        "c": {"cap_base": c_base, "cap_dual": 0, "cap_tes": 0, "dem": res_c["dem"], "dg_kva": res_c["dg_kva"], "opex": res_c["opex"], "capex": cap_c, "bk": bk_c, "data": res_c},
        "p": {"cap_base": p_base, "cap_dual": p_dual, "cap_tes": p_tes, "dem": res_p["dem"], "dg_kva": res_p["dg_kva"], "opex": res_p["opex"], "capex": cap_p, "bk": bk_p, "pb": pb_p, "data": res_p},
        "s": {"cap_base": s_base, "cap_dual": 0, "cap_tes": s_tes, "dem": res_s["dem"], "dg_kva": res_s["dg_kva"], "opex": res_s["opex"], "capex": cap_s, "bk": bk_s, "pb": pb_s, "data": res_s}
    }