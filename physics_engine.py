"""
CETP Digital Twin - Physics & Thermodynamics Engine
File: physics_engine.py
"""
import numpy as np
import pandas as pd

def expand_24_to_8760(arr_24):
    """Extrapolates 24-hour diurnal profile to 8,760 hours for annual OPEX."""
    return np.tile(arr_24, 365)

def calc_pump_kw(flow_m3h: float, head_m: float, eff: float = 0.75) -> float:
    """Hydraulic pump power calculation."""
    if flow_m3h <= 0 or head_m <= 0: return 0.0
    m_dot_kgs = (flow_m3h * 1000.0) / 3600.0
    return (9.81 * m_dot_kgs * head_m) / (eff * 1000.0)

def get_compressor_kw_tr(load_factor: float, is_brine: bool = False, is_night: bool = False) -> float:
    """Dynamic PLV and ambient relief degradation curves."""
    if load_factor <= 0.0: return 0.0
    
    # Base efficiency (Water Cooled)
    base_eff = 0.85 if is_brine else 0.62 
    
    # Part Load Value Multipliers
    if load_factor < 0.3:
        plv = 1.20
    elif load_factor < 0.5:
        plv = 1.05
    elif load_factor < 0.9:
        plv = 0.95
    else:
        plv = 1.00
        
    night_relief = 0.92 if is_night else 1.00
    return base_eff * plv * night_relief

def simulate_conventional(load_24, tar_24, total_fleet_tr):
    kw_comp, kw_pump, kw_ct = [], [], []
    for h, tr in enumerate(load_24):
        is_night = (h >= 22 or h <= 6)
        lf = min(1.0, tr / max(1.0, total_fleet_tr))
        
        c_kw = tr * get_compressor_kw_tr(lf, False, is_night)
        flow_ratio = max(0.4, lf)
        p_kw = 45.0 * (flow_ratio ** 3) # VFD Affinity Law
        ct_kw = 30.0 * flow_ratio
        
        kw_comp.append(c_kw)
        kw_pump.append(p_kw)
        kw_ct.append(ct_kw)
        
    tot_kw = np.array(kw_comp) + np.array(kw_pump) + np.array(kw_ct)
    cost_24 = tot_kw * tar_24
    
    return {
        "comp_kw": np.array(kw_comp), "pump_kw": np.array(kw_pump), "ct_kw": np.array(kw_ct),
        "total_kw": tot_kw, "daily_opex": np.sum(cost_24), "annual_opex": np.sum(cost_24) * 365
    }

def simulate_pcm(load_24, tar_24, fleet_tr, tes_trh, charge_chiller_tr):
    storage = 0.0
    kw_comp, kw_pump, mode = [], [], []
    
    # Find lowest 8-hour tariff block
    rolling_8 = [sum(tar_24[(i+j)%24] for j in range(8)) for i in range(24)]
    charge_start = np.argmin(rolling_8)
    charge_hrs = [(charge_start + j)%24 for j in range(8)]
    peak_hrs = np.argsort(tar_24)[::-1][:5] # Top 5 peak hours
    
    for h, tr in enumerate(load_24):
        c_kw, p_kw, c_mode = 0.0, 0.0, "NORMAL"
        is_night = (h >= 22 or h <= 6)
        
        if h in charge_hrs:
            c_mode = "CHARGING"
            c_kw += charge_chiller_tr * get_compressor_kw_tr(1.0, True, True)
            p_kw += 30.0 # Extra brine pump + PHE penalty
            storage = min(tes_trh, storage + charge_chiller_tr)
            
            # Base plant handles facility load
            lf = tr / max(1.0, fleet_tr)
            c_kw += tr * get_compressor_kw_tr(lf, False, is_night)
            p_kw += 45.0 * (max(0.4, lf)**3)
            
        elif h in peak_hrs and storage > 0:
            discharged = min(tr, storage)
            storage -= discharged
            rem_load = tr - discharged
            c_mode = "DISCHARGE" if rem_load == 0 else "PARTIAL DISCHARGE"
            
            if rem_load > 0:
                lf = rem_load / max(1.0, fleet_tr)
                c_kw += rem_load * get_compressor_kw_tr(lf, False, False)
            p_kw += 55.0 # High secondary pump flow
            
        else:
            lf = tr / max(1.0, fleet_tr)
            c_kw += tr * get_compressor_kw_tr(lf, False, is_night)
            p_kw += 45.0 * (max(0.4, lf)**3)
            
        kw_comp.append(c_kw)
        kw_pump.append(p_kw)
        mode.append(c_mode)
        
    tot_kw = np.array(kw_comp) + np.array(kw_pump)
    cost_24 = tot_kw * tar_24
    
    return {
        "comp_kw": np.array(kw_comp), "pump_kw": np.array(kw_pump), "mode": mode,
        "total_kw": tot_kw, "daily_opex": np.sum(cost_24), "annual_opex": np.sum(cost_24) * 365
    }

def simulate_stratified(load_24, tar_24, fleet_tr, tes_trh):
    storage = 0.0
    kw_comp, kw_pump, mode = [], [], []
    
    low_tar_thresh = np.percentile(tar_24, 35)
    peak_tar_thresh = np.percentile(tar_24, 75)
    
    for h, tr in enumerate(load_24):
        c_kw, p_kw, c_mode = 0.0, 0.0, "NORMAL"
        is_night = (h >= 22 or h <= 6)
        spare_cap = max(0.0, fleet_tr - tr)
        
        if tar_24[h] <= low_tar_thresh and spare_cap > 50:
            c_mode = "CHARGING"
            charge_tr = min(spare_cap, (tes_trh - storage)/2.0)
            storage = min(tes_trh, storage + charge_tr)
            
            tot_tr = tr + charge_tr
            lf = tot_tr / max(1.0, fleet_tr)
            c_kw = tot_tr * get_compressor_kw_tr(lf, False, is_night)
            p_kw = 45.0
            
        elif tar_24[h] >= peak_tar_thresh and storage > 0:
            discharged = min(tr, storage)
            storage -= discharged
            rem_load = tr - discharged
            c_mode = "DISCHARGE" if rem_load == 0 else "PARTIAL DISCHARGE"
            
            if rem_load > 0:
                lf = rem_load / max(1.0, fleet_tr)
                c_kw += rem_load * get_compressor_kw_tr(lf, False, False)
            p_kw = 35.0
            
        else:
            lf = tr / max(1.0, fleet_tr)
            c_kw += tr * get_compressor_kw_tr(lf, False, is_night)
            p_kw += 45.0 * (max(0.4, lf)**3)
            
        kw_comp.append(c_kw)
        kw_pump.append(p_kw)
        mode.append(c_mode)
        
    tot_kw = np.array(kw_comp) + np.array(kw_pump)
    cost_24 = tot_kw * tar_24
    
    return {
        "comp_kw": np.array(kw_comp), "pump_kw": np.array(kw_pump), "mode": mode,
        "total_kw": tot_kw, "daily_opex": np.sum(cost_24), "annual_opex": np.sum(cost_24) * 365
    }