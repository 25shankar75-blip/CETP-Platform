"""
Cooling Energy Transition Platform (CETP) - Physics & Dual-Benefit Engine
File: physics_engine.py
"""
import numpy as np
import pandas as pd

def calc_tr(flow_m3h, dt_c, fluid="water"):
    """Calculates TR from m * Cp * Delta_T"""
    cp = 4.186 if fluid == "water" else 3.65
    rho = 1000.0 if fluid == "water" else 1035.0
    m_dot_kgs = (flow_m3h * rho) / 3600.0
    return max(0.0, (m_dot_kgs * cp * dt_c) / 3.51685)

def calc_pump_kw(flow_m3h, head_m, eff=0.75):
    """Calculates hydraulic pump power."""
    m_dot_kgs = (flow_m3h * 1000.0) / 3600.0
    return max(0.0, (9.81 * m_dot_kgs * head_m) / (eff * 1000.0))

def get_plv_kw_tr(load_factor, is_brine=False, is_night=False):
    """Dynamic Chiller Efficiency Curve."""
    if load_factor <= 0: return 0.0
    base = 0.85 if is_brine else 0.62
    if load_factor < 0.3: plv = 1.25
    elif load_factor < 0.5: plv = 1.10
    elif load_factor < 0.85: plv = 0.95
    else: plv = 1.00
    night_relief = 0.92 if is_night else 1.00
    return base * plv * night_relief

def simulate_conventional(load_24, tar_24, fleet_tr, scope, audit_cfg: dict):
    comp, chw, cw, ct, charge, discharge = [], [], [], [], [], []
    
    # Pre-calculate Inefficient Audited State (if Brownfield)
    if scope == "Brownfield (Retrofit)":
        dt_actual = max(1.0, audit_cfg.get("run_chw_ret_c", 12) - audit_cfg.get("run_chw_sup_c", 8))
        tr_actual = calc_tr(audit_cfg.get("run_chw_flow_m3h", 500), dt_actual)
        kw_chw = calc_pump_kw(audit_cfg.get("run_chw_flow_m3h", 500), audit_cfg.get("run_chw_head_m", 30))
        kw_cw = calc_pump_kw(audit_cfg.get("run_cw_flow_m3h", 600), audit_cfg.get("run_cw_head_m", 25))
        kw_ct = audit_cfg.get("run_ct_fan_kw", 45.0)
        actual_kw_tr = ((tr_actual * 0.72) + kw_chw + kw_cw + kw_ct) / max(1.0, tr_actual) if tr_actual > 0 else 0.95

    for h, tr in enumerate(load_24):
        charge.append(0.0); discharge.append(0.0)
        
        if scope == "Brownfield (Retrofit)":
            # Inefficient Flat Profile
            comp.append(tr * actual_kw_tr)
            chw.append(kw_chw)
            cw.append(kw_cw)
            ct.append(kw_ct)
        else:
            # Greenfield Optimized Design State
            lf = min(1.0, tr / max(1.0, fleet_tr))
            flow_ratio = max(0.4, lf)
            comp.append(tr * get_plv_kw_tr(lf, False, (h>=22 or h<=6)))
            chw.append(35.0 * (flow_ratio ** 3)) # Affinity Laws
            cw.append(40.0 * (flow_ratio ** 3))
            ct.append(25.0 * flow_ratio)
            
    tot_kw = np.array(comp) + np.array(chw) + np.array(cw) + np.array(ct)
    cost = tot_kw * tar_24
    
    return {
        "cooling_tr": load_24, "charge_tr": charge, "discharge_tr": discharge,
        "comp_kw": comp, "chw_pump_kw": chw, "cw_pump_kw": cw, "ct_fan_kw": ct,
        "total_kw": tot_kw, "tariff": tar_24, "hourly_cost": cost,
        "annual_opex": np.sum(cost) * 365.0
    }

def simulate_pcm(load_24, tar_24, fleet_tr, tes_trh, charge_chiller_tr):
    comp, chw, cw, ct, charge, discharge = [], [], [], [], [], []
    storage = 0.0
    
    # 8-hr Arbitrage Window
    rolling_8 = [sum(tar_24[(i+j)%24] for j in range(8)) for i in range(24)]
    c_start = np.argmin(rolling_8)
    charge_hrs = [(c_start + j)%24 for j in range(8)]
    peak_hrs = np.argsort(tar_24)[::-1][:6]
    
    for h, tr in enumerate(load_24):
        c_k, chw_k, cw_k, ct_k, c_tr, d_tr = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
        is_night = (h >= 22 or h <= 6)
        
        # Benefit 1: TES Options ALWAYS assume Thermodynamic Restoration (VFDs active, proper flow)
        if h in charge_hrs:
            c_tr = charge_chiller_tr
            c_k += charge_chiller_tr * get_plv_kw_tr(1.0, True, True)
            storage = min(tes_trh, storage + c_tr)
            
            lf = tr / max(1.0, fleet_tr)
            c_k += tr * get_plv_kw_tr(lf, False, is_night)
            chw_k = 35.0 * (max(0.4, lf)**3) + 20.0 # Restored VFD + Brine Pump
            cw_k = 40.0 * (max(0.4, lf)**3) + 25.0
            ct_k = 25.0 * max(0.4, lf) + 15.0
            
        elif h in peak_hrs and storage > 0:
            d_tr = min(tr, storage)
            storage -= d_tr
            rem = tr - d_tr
            if rem > 0:
                lf = rem / max(1.0, fleet_tr)
                c_k += rem * get_plv_kw_tr(lf, False, False)
                chw_k = 35.0 * (max(0.4, lf)**3)
                cw_k = 40.0 * (max(0.4, lf)**3)
                ct_k = 25.0 * max(0.4, lf)
            else:
                chw_k = 35.0 # Only secondary pumps run
                cw_k = 0.0
                ct_k = 0.0
        else:
            lf = tr / max(1.0, fleet_tr)
            c_k += tr * get_plv_kw_tr(lf, False, is_night)
            chw_k = 35.0 * (max(0.4, lf)**3)
            cw_k = 40.0 * (max(0.4, lf)**3)
            ct_k = 25.0 * max(0.4, lf)
            
        charge.append(c_tr); discharge.append(d_tr)
        comp.append(c_k); chw.append(chw_k); cw.append(cw_k); ct.append(ct_k)
        
    tot_kw = np.array(comp) + np.array(chw) + np.array(cw) + np.array(ct)
    cost = tot_kw * tar_24
    
    return {
        "cooling_tr": load_24, "charge_tr": charge, "discharge_tr": discharge,
        "comp_kw": comp, "chw_pump_kw": chw, "cw_pump_kw": cw, "ct_fan_kw": ct,
        "total_kw": tot_kw, "tariff": tar_24, "hourly_cost": cost,
        "annual_opex": np.sum(cost) * 365.0
    }

def simulate_stratified(load_24, tar_24, fleet_tr, tes_trh):
    comp, chw, cw, ct, charge, discharge = [], [], [], [], [], []
    storage = 0.0
    low_tar = np.percentile(tar_24, 40)
    peak_tar = np.percentile(tar_24, 75)
    
    for h, tr in enumerate(load_24):
        c_k, chw_k, cw_k, ct_k, c_tr, d_tr = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
        spare = max(0.0, fleet_tr - tr)
        is_night = (h >= 22 or h <= 6)
        
        if tar_24[h] <= low_tar and spare > 50:
            c_tr = min(spare, (tes_trh - storage)/2.0)
            storage = min(tes_trh, storage + c_tr)
            tot_tr = tr + c_tr
            lf = tot_tr / max(1.0, fleet_tr)
            c_k = tot_tr * get_plv_kw_tr(lf, False, is_night)
            chw_k = 35.0 * (max(0.4, lf)**3)
            cw_k = 40.0 * (max(0.4, lf)**3)
            ct_k = 25.0 * max(0.4, lf)
            
        elif tar_24[h] >= peak_tar and storage > 0:
            d_tr = min(tr, storage)
            storage -= d_tr
            rem = tr - d_tr
            if rem > 0:
                lf = rem / max(1.0, fleet_tr)
                c_k = rem * get_plv_kw_tr(lf, False, False)
                chw_k = 35.0 * (max(0.4, lf)**3)
                cw_k = 40.0 * (max(0.4, lf)**3)
                ct_k = 25.0 * max(0.4, lf)
            else:
                chw_k = 35.0
                cw_k = 0.0
                ct_k = 0.0
        else:
            lf = tr / max(1.0, fleet_tr)
            c_k = tr * get_plv_kw_tr(lf, False, is_night)
            chw_k = 35.0 * (max(0.4, lf)**3)
            cw_k = 40.0 * (max(0.4, lf)**3)
            ct_k = 25.0 * max(0.4, lf)
            
        charge.append(c_tr); discharge.append(d_tr)
        comp.append(c_k); chw.append(chw_k); cw.append(cw_k); ct.append(ct_k)
        
    tot_kw = np.array(comp) + np.array(chw) + np.array(cw) + np.array(ct)
    cost = tot_kw * tar_24
    
    return {
        "cooling_tr": load_24, "charge_tr": charge, "discharge_tr": discharge,
        "comp_kw": comp, "chw_pump_kw": chw, "cw_pump_kw": cw, "ct_fan_kw": ct,
        "total_kw": tot_kw, "tariff": tar_24, "hourly_cost": cost,
        "annual_opex": np.sum(cost) * 365.0
    }