"""
CETP Digital Twin - ASHRAE Physics & Dispatch Engine
File: physics_engine.py
"""

import numpy as np
import pandas as pd

def calc_operating_tr(flow_m3h: float, dt_c: float, fluid_type: str = "water") -> float:
    rho = 1000.0 if fluid_type == "water" else 1035.0
    cp = 4.186 if fluid_type == "water" else 3.65  # kJ/kg.K
    m_dot_kgs = (flow_m3h * rho) / 3600.0
    kw_thermal = m_dot_kgs * cp * dt_c
    tr = kw_thermal / 3.51685
    return max(0.0, tr)

def calc_hydraulic_pump_kw(flow_m3h: float, head_m: float, pump_eff: float = 0.75) -> float:
    m_dot_kgs = (flow_m3h * 1000.0) / 3600.0
    power_kw = (9.81 * m_dot_kgs * head_m) / (pump_eff * 1000.0)
    return max(0.0, power_kw)

def get_chiller_kw_per_tr(load_factor: float, base_kw_tr: float = 0.65, is_night: bool = False) -> float:
    if load_factor <= 0.0:
        return 0.0
    elif load_factor < 0.3:
        plv_mult = 1.25
    elif load_factor < 0.5:
        plv_mult = 1.10
    elif load_factor < 0.85:
        plv_mult = 0.95
    else:
        plv_mult = 1.00
    
    night_mult = 0.92 if is_night else 1.00
    return base_kw_tr * plv_mult * night_mult

def simulate_24h_plant(df_24h: pd.DataFrame, scope: str, audit_config: dict, total_fleet_tr: float):
    hours = df_24h["Hour"].values
    loads = df_24h["Cooling Load (TR)"].values
    tariffs = df_24h["Tariff (₹/kWh)"].values
    
    comp_kw = []
    chw_pump_kw = []
    cw_pump_kw = []
    ct_fan_kw = []
    
    if scope == "Brownfield (Retrofit)":
        actual_kw_tr = audit_config.get("actual_kw_per_tr", 0.91)
        audit_chw_kw = calc_hydraulic_pump_kw(audit_config.get("running_chw_flow_m3h", 500), audit_config.get("chw_pump_head_m", 30))
        audit_cw_kw = calc_hydraulic_pump_kw(audit_config.get("running_cw_flow_m3h", 600), audit_config.get("cw_pump_head_m", 25))
        audit_ct_kw = audit_config.get("ct_fan_power_kw", 45.0)
        
        for h, load in zip(hours, loads):
            comp_kw.append(load * actual_kw_tr)
            chw_pump_kw.append(audit_chw_kw)
            cw_pump_kw.append(audit_cw_kw)
            ct_fan_kw.append(audit_ct_kw)
    else:
        for h, load in zip(hours, loads):
            is_night = (h >= 22 or h <= 6)
            lf = min(1.0, load / max(1.0, total_fleet_tr))
            kw_tr = get_chiller_kw_per_tr(lf, base_kw_tr=0.62, is_night=is_night)
            comp_kw.append(load * kw_tr)
            
            flow_ratio = max(0.4, load / max(1.0, total_fleet_tr))
            chw_pump_kw.append(35.0 * (flow_ratio ** 3))
            cw_pump_kw.append(40.0 * (flow_ratio ** 3))
            ct_fan_kw.append(25.0 * flow_ratio)
            
    total_kw = np.array(comp_kw) + np.array(chw_pump_kw) + np.array(cw_pump_kw) + np.array(ct_fan_kw)
    hourly_cost = total_kw * tariffs
    
    return {
        "comp_kw": np.array(comp_kw),
        "chw_pump_kw": np.array(chw_pump_kw),
        "cw_pump_kw": np.array(cw_pump_kw),
        "ct_fan_kw": np.array(ct_fan_kw),
        "total_kw": total_kw,
        "hourly_cost": hourly_cost,
        "daily_opex": np.sum(hourly_cost),
        "annual_opex": np.sum(hourly_cost) * 365.0
    }

def simulate_pcm_tes_24h(df_24h: pd.DataFrame, tes_capacity_trh: float, charge_chiller_tr: float, fleet_installed_tr: float):
    hours = df_24h["Hour"].values
    loads = df_24h["Cooling Load (TR)"].values
    tariffs = df_24h["Tariff (₹/kWh)"].values
    
    # 1. Identify continuous 8-hour window with lowest sum of tariffs
    rolling_8h = [np.sum([tariffs[(i+j)%24] for j in range(8)]) for i in range(24)]
    best_start = np.argmin(rolling_8h)
    charge_hours = [(best_start + j) % 24 for j in range(8)]
    
    peak_hours_idx = np.argsort(tariffs)[::-1][:6]
    
    storage_state = 0.0
    charge_kw = []
    base_chiller_kw = []
    sec_pump_kw = []
    mode = []
    
    for i in range(24):
        h = hours[i]
        load = loads[i]
        t = tariffs[i]
        is_charge = (i in charge_hours)
        is_peak = (i in peak_hours_idx)
        
        c_kw = 0.0
        b_kw = 0.0
        p_kw = 25.0
        
        if is_charge:
            c_kw = charge_chiller_tr * 0.82
            storage_state = min(tes_capacity_trh, storage_state + charge_chiller_tr)
            lf = load / max(1.0, fleet_installed_tr)
            b_kw = load * get_chiller_kw_per_tr(lf, base_kw_tr=0.62, is_night=(h >= 22 or h <= 6))
            mode.append("CHARGING")
        elif is_peak and storage_state > 0:
            discharged_tr = min(load, storage_state)
            storage_state -= discharged_tr
            remaining_load = load - discharged_tr
            if remaining_load > 0:
                lf = remaining_load / max(1.0, fleet_installed_tr)
                b_kw = remaining_load * get_chiller_kw_per_tr(lf, base_kw_tr=0.62)
            p_kw = 38.0
            mode.append("FULL DISCHARGE" if remaining_load == 0 else "PARTIAL DISCHARGE")
        else:
            lf = load / max(1.0, fleet_installed_tr)
            b_kw = load * get_chiller_kw_per_tr(lf, base_kw_tr=0.62, is_night=(h >= 22 or h <= 6))
            mode.append("NORMAL")
            
        charge_kw.append(c_kw)
        base_chiller_kw.append(b_kw)
        sec_pump_kw.append(p_kw)
        
    total_kw = np.array(charge_kw) + np.array(base_chiller_kw) + np.array(sec_pump_kw)
    hourly_cost = total_kw * tariffs
    
    return {
        "charge_kw": np.array(charge_kw),
        "base_chiller_kw": np.array(base_chiller_kw),
        "pump_kw": np.array(sec_pump_kw),
        "total_kw": total_kw,
        "hourly_cost": hourly_cost,
        "daily_opex": np.sum(hourly_cost),
        "annual_opex": np.sum(hourly_cost) * 365.0,
        "mode": mode,
        "charge_start_hour": charge_hours[0] + 1
    }

def simulate_stratified_tes_24h(df_24h: pd.DataFrame, tes_capacity_trh: float, fleet_installed_tr: float):
    hours = df_24h["Hour"].values
    loads = df_24h["Cooling Load (TR)"].values
    tariffs = df_24h["Tariff (₹/kWh)"].values
    
    low_tariff_thresh = np.percentile(tariffs, 40)
    peak_tariff_thresh = np.percentile(tariffs, 75)
    
    storage_state = 0.0
    comp_kw = []
    pump_kw = []
    mode = []
    
    for i in range(24):
        h = hours[i]
        load = loads[i]
        t = tariffs[i]
        
        avail_tr = max(0.0, fleet_installed_tr - load)
        
        if t <= low_tariff_thresh and avail_tr > 100:
            charge_tr = min(avail_tr, (tes_capacity_trh - storage_state) / 2.0)
            storage_state = min(tes_capacity_trh, storage_state + charge_tr)
            total_chiller_tr = load + charge_tr
            lf = total_chiller_tr / max(1.0, fleet_installed_tr)
            c_kw = total_chiller_tr * get_chiller_kw_per_tr(lf, base_kw_tr=0.62, is_night=(h >= 22 or h <= 6))
            p_kw = 42.0
            mode.append("CHARGING")
        elif t >= peak_tariff_thresh and storage_state > 0:
            discharge_tr = min(load, storage_state)
            storage_state -= discharge_tr
            rem_load = load - discharge_tr
            lf = rem_load / max(1.0, fleet_installed_tr)
            c_kw = rem_load * get_chiller_kw_per_tr(lf, base_kw_tr=0.62)
            p_kw = 35.0
            mode.append("FULL DISCHARGE" if rem_load == 0 else "PARTIAL DISCHARGE")
        else:
            lf = load / max(1.0, fleet_installed_tr)
            c_kw = load * get_chiller_kw_per_tr(lf, base_kw_tr=0.62, is_night=(h >= 22 or h <= 6))
            p_kw = 30.0
            mode.append("NORMAL")
            
        comp_kw.append(c_kw)
        pump_kw.append(p_kw)
        
    total_kw = np.array(comp_kw) + np.array(pump_kw)
    hourly_cost = total_kw * tariffs
    
    return {
        "comp_kw": np.array(comp_kw),
        "pump_kw": np.array(pump_kw),
        "total_kw": total_kw,
        "hourly_cost": hourly_cost,
        "daily_opex": np.sum(hourly_cost),
        "annual_opex": np.sum(hourly_cost) * 365.0,
        "mode": mode
    }