# optimizer.py
import numpy as np
from physics_engine import get_plv_kw_tr, get_night_condenser_bonus, calc_pump_ikw_tr, calc_vfd_pump_power
from financial_engine import calculate_capex

def run_thermodynamic_simulation(load_prof, tariff_prof, cap_base, cap_dual, tes_cap, charge_hours, prm):
    n_hrs = len(load_prof)
    hr_of_day = np.arange(n_hrs) % 24
    
    pwr_comp, pwr_brine, pwr_chw, pwr_cw, pwr_fan, pwr_total = np.zeros(n_hrs), np.zeros(n_hrs), np.zeros(n_hrs), np.zeros(n_hrs), np.zeros(n_hrs), np.zeros(n_hrs)
    charge_tr, discharge_tr = np.zeros(n_hrs), np.zeros(n_hrs)
    
    kw_tr_base = prm['kw_tr_base']
    kw_tr_brine = prm['kw_tr_brine']
    dt_chw = abs(prm['chw_return'] - prm['chw_supply'])
    
    chw_pmp = calc_pump_ikw_tr(dt_chw, prm['head_chw'], prm['pump_efficiency'])
    cw_pmp = calc_pump_ikw_tr(5.0, prm['head_cw'], prm['pump_efficiency'])
    brine_pmp = calc_pump_ikw_tr(5.0, 40.0, prm['pump_efficiency'], True)
    
    for i in range(n_hrs):
        load, hr = load_prof[i], hr_of_day[i]
        is_night, bonus = hr in charge_hours, get_night_condenser_bonus(hr)
        
        if tes_cap == 0:
            vfd = load / cap_base if cap_base > 0 else 1.0
            pwr_comp[i] = load * get_plv_kw_tr(vfd, kw_tr_base) * bonus
            pwr_chw[i] = calc_vfd_pump_power(chw_pmp, load, cap_base)
            pwr_cw[i] = calc_vfd_pump_power(cw_pmp, load, cap_base) if "Water" in prm['chiller_type'] else 0
            pwr_fan[i] = prm['ct_fan_ikw_tr'] * load * (vfd**2) if "Water" in prm['chiller_type'] else 0
        else: 
            if is_night:
                b_load = min(cap_base, load)
                vfd = b_load / cap_base if cap_base > 0 else 1.0
                pwr_comp[i] = b_load * get_plv_kw_tr(vfd, kw_tr_base) * bonus
                pwr_brine[i] = cap_dual * kw_tr_brine * bonus if cap_dual > 0 else 0
                pwr_chw[i] = calc_vfd_pump_power(chw_pmp, b_load, cap_base) + (cap_dual * brine_pmp if cap_dual > 0 else calc_vfd_pump_power(chw_pmp, tes_cap/len(charge_hours), cap_base))
                pwr_cw[i] = calc_vfd_pump_power(cw_pmp, b_load + cap_dual + (tes_cap/len(charge_hours) if cap_dual==0 else 0), cap_base + cap_dual) if "Water" in prm['chiller_type'] else 0
                pwr_fan[i] = prm['ct_fan_ikw_tr'] * (b_load + cap_dual + (tes_cap/len(charge_hours) if cap_dual==0 else 0)) if "Water" in prm['chiller_type'] else 0
                charge_tr[i] = cap_dual if cap_dual > 0 else tes_cap/len(charge_hours)
            else:
                b_load = cap_base if load > cap_base else load
                disch = load - cap_base if load > cap_base else 0
                vfd = b_load / cap_base if cap_base > 0 else 1.0
                pwr_comp[i] = b_load * get_plv_kw_tr(vfd, kw_tr_base) * bonus
                pwr_chw[i] = calc_vfd_pump_power(chw_pmp, b_load, cap_base) + (disch * chw_pmp)
                pwr_cw[i] = calc_vfd_pump_power(cw_pmp, b_load, cap_base) if "Water" in prm['chiller_type'] else 0
                pwr_fan[i] = prm['ct_fan_ikw_tr'] * b_load * (vfd**2) if "Water" in prm['chiller_type'] else 0
                discharge_tr[i] = disch
                
        pwr_total[i] = pwr_comp[i] + pwr_brine[i] + pwr_chw[i] + pwr_cw[i] + pwr_fan[i]

    dem_kw = float(np.max(pwr_total))
    dg_kva = (dem_kw / 0.8) * 1.25
    opex = np.sum(pwr_total * tariff_prof) + (dg_kva * prm['demand_rate'] * 12)
    return {
        "kw_comp": pwr_comp, "kw_brine": pwr_brine, "kw_chw": pwr_chw, "kw_cw": pwr_cw, "kw_fan": pwr_fan, "total_kw": pwr_total,
        "charge": charge_tr, "discharge": discharge_tr, "dem": dem_kw, "dg_kva": dg_kva, "opex": opex
    }

def optimize_plant(L8760, T8760, peak_tr, charge_hrs, prm, proj_type):
    scale = peak_tr / 2794.18
    c_base = peak_tr * 1.25
    res_c = run_thermodynamic_simulation(L8760, T8760, c_base, 0, 0, charge_hrs, prm)
    bk_c, cap_c = calculate_capex(c_base, 0, 0, "Conventional N+1", prm, res_c["dg_kva"], c_base, proj_type)
    
    p_base, p_tes, p_dual = 2418.0 * scale, 1512.10 * scale, 189.0 * scale
    res_p = run_thermodynamic_simulation(L8760, T8760, p_base, p_dual, p_tes, charge_hrs, prm)
    bk_p, cap_p = calculate_capex(p_base, p_dual, p_tes, "PCM TES", prm, res_p["dg_kva"], c_base, proj_type)
    
    s_base, s_tes = 2280.0 * scale, 2068.0 * scale
    res_s = run_thermodynamic_simulation(L8760, T8760, s_base, 0, s_tes, charge_hrs, prm)
    bk_s, cap_s = calculate_capex(s_base, 0, s_tes, "Stratified TES", prm, res_s["dg_kva"], c_base, proj_type)
    
    pb_p = (cap_p - cap_c) / (res_c['opex'] - res_p['opex']) if (res_c['opex'] - res_p['opex']) > 0 else 0
    pb_s = (cap_s - cap_c) / (res_c['opex'] - res_s['opex']) if (res_c['opex'] - res_s['opex']) > 0 else 0
    
    return {
        "c": {"cap_base": c_base, "cap_dual": 0, "cap_tes": 0, "dem": res_c["dem"], "dg_kva": res_c["dg_kva"], "opex": res_c["opex"], "capex": cap_c, "bk": bk_c, "data": res_c},
        "p": {"cap_base": p_base, "cap_dual": p_dual, "cap_tes": p_tes, "dem": res_p["dem"], "dg_kva": res_p["dg_kva"], "opex": res_p["opex"], "capex": cap_p, "bk": bk_p, "pb": pb_p, "data": res_p},
        "s": {"cap_base": s_base, "cap_dual": 0, "cap_tes": s_tes, "dem": res_s["dem"], "dg_kva": res_s["dg_kva"], "opex": res_s["opex"], "capex": cap_s, "bk": bk_s, "pb": pb_s, "data": res_s}
    }