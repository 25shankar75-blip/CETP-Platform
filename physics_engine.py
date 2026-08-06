"""
Cooling Energy Transition Platform (CETP) - ASHRAE Thermodynamics, Live Weather & Dispatch Engine
File: physics_engine.py
"""

import numpy as np
import pandas as pd
import urllib.request
import json

def expand_24_to_8760(arr_24: np.ndarray) -> np.ndarray:
    """Extrapolates 24-hour diurnal profile across 8,760 annual operating hours."""
    return np.tile(arr_24, 365)

def fetch_live_weather_wbt(location_str: str = "Ujjain, MP", lat: float = 23.1765, lon: float = 75.7885) -> dict:
    """Fetches real-time/historical hourly WBT and DBT via Open-Meteo API with fallback."""
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,relative_humidity_2m&forecast_days=1"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=3) as response:
            data = json.loads(response.read().decode())
            dbt = data["hourly"]["temperature_2m"][:24]
            rh = data["hourly"]["relative_humidity_2m"][:24]
            wbt = [
                d * np.arctan(0.151977 * (r + 8.313659)**0.5) + np.arctan(d + r) - np.arctan(r - 1.676331) + 0.00391838 * (r**1.5) * np.arctan(0.023101 * r) - 4.686035
                for d, r in zip(dbt, rh)
            ]
            return {"dbt": dbt, "wbt": wbt, "status": "LIVE_API"}
    except Exception:
        hours = np.arange(24)
        dbt_synthetic = [28.0 + 8.0 * np.sin((h - 8) * np.pi / 12) for h in hours]
        wbt_synthetic = [22.0 + 5.0 * np.sin((h - 8) * np.pi / 12) for h in hours]
        return {"dbt": dbt_synthetic, "wbt": wbt_synthetic, "status": "SYNTHETIC_FALLBACK"}

def calc_operating_tr(flow_m3h: float, dt_c: float, fluid_type: str = "water") -> float:
    """Auto-calculates operating TR: m * Cp * Delta_T."""
    if flow_m3h <= 0 or dt_c <= 0:
        return 0.0
    rho = 1000.0 if fluid_type == "water" else 1035.0
    cp = 4.186 if fluid_type == "water" else 3.65  # kJ/kg.K
    m_dot_kgs = (flow_m3h * rho) / 3600.0
    kw_thermal = m_dot_kgs * cp * dt_c
    return kw_thermal / 3.51685

def calc_hydraulic_pump_kw(flow_m3h: float, head_m: float, pump_eff: float = 0.75) -> float:
    """Calculates hydraulic pump power from flow (m3/h) and head (m)."""
    if flow_m3h <= 0 or head_m <= 0:
        return 0.0
    m_dot_kgs = (flow_m3h * 1000.0) / 3600.0
    return (9.81 * m_dot_kgs * head_m) / (pump_eff * 1000.0)

def get_chiller_kw_per_tr(load_factor: float, base_kw_tr: float = 0.62, is_air_cooled: bool = False, is_night: bool = False) -> float:
    """Dynamic Chiller Part-Load Value (PLV) degradation curve with night condenser relief."""
    if load_factor <= 0.0:
        return 0.0
    if load_factor < 0.3:
        plv_mult = 1.25
    elif load_factor < 0.5:
        plv_mult = 1.10
    elif load_factor < 0.85:
        plv_mult = 0.95
    else:
        plv_mult = 1.00
    
    type_mult = 1.35 if is_air_cooled else 1.00
    night_mult = 0.92 if is_night else 1.00
    return base_kw_tr * plv_mult * type_mult * night_mult

def simulate_24h_plant(df_24h: pd.DataFrame, scope: str, audit_config: dict, fleet_df: pd.DataFrame):
    """Simulates Baseline Plant operation (Retrofit Audited Inefficient vs Greenfield Proposed N+1)."""
    hours = df_24h["Hour"].values
    loads = df_24h["Cooling Load (TR)"].values
    tariffs = df_24h["Tariff (₹/kWh)"].values
    
    total_fleet_tr = sum(fleet_df["Capacity (TR)"] * fleet_df["Quantity"]) if not fleet_df.empty else max(loads) * 1.25
    is_any_ac = any("Air-Cooled" in str(t) for t in fleet_df["Chiller Type"]) if not fleet_df.empty else False

    op_tr, charge_tr, discharge_tr = [], [], []
    comp_kw, chw_pri_kw, chw_sec_kw, cw_pump_kw, ct_fan_kw = [], [], [], [], []
    lf_list = []

    if scope == "Brownfield (Retrofit)":
        dt_actual = max(1.0, audit_config.get("running_chw_return_c", 12.0) - audit_config.get("running_chw_supply_c", 8.0))
        tr_measured = calc_operating_tr(audit_config.get("running_chw_flow_m3h", 500.0), dt_actual)
        
        chw_pri = calc_hydraulic_pump_kw(audit_config.get("running_chw_flow_m3h", 500.0), audit_config.get("chw_pump_head_m", 30.0))
        chw_sec = chw_pri * 0.4
        cw_p = 0.0 if is_any_ac else calc_hydraulic_pump_kw(audit_config.get("running_cw_flow_m3h", 600.0), audit_config.get("cw_pump_head_m", 25.0))
        ct_f = 0.0 if is_any_ac else audit_config.get("ct_fan_power_kw", 45.0)
        
        tot_aux_kw = chw_pri + chw_sec + cw_p + ct_f
        actual_kw_tr = (tr_measured * 0.72 + tot_aux_kw) / max(1.0, tr_measured) if tr_measured > 0 else 0.91

        for h, load in zip(hours, loads):
            op_tr.append(load)
            charge_tr.append(0.0)
            discharge_tr.append(0.0)
            lf = min(1.0, load / max(1.0, total_fleet_tr))
            lf_list.append(lf * 100.0)
            
            comp_kw.append(load * actual_kw_tr)
            chw_pri_kw.append(chw_pri)
            chw_sec_kw.append(chw_sec)
            cw_pump_kw.append(cw_p)
            ct_fan_kw.append(ct_f)
    else:
        for h, load in zip(hours, loads):
            is_night = (h >= 22 or h <= 6)
            lf = min(1.0, load / max(1.0, total_fleet_tr))
            lf_list.append(lf * 100.0)
            op_tr.append(load)
            charge_tr.append(0.0)
            discharge_tr.append(0.0)
            
            kw_tr = get_chiller_kw_per_tr(lf, base_kw_tr=0.62, is_air_cooled=is_any_ac, is_night=is_night)
            comp_kw.append(load * kw_tr)
            
            flow_r = max(0.4, load / max(1.0, total_fleet_tr))
            chw_pri_kw.append(25.0 * flow_r)
            chw_sec_kw.append(15.0 * (flow_r ** 3)) # VFD Affinity Law
            cw_pump_kw.append(0.0 if is_any_ac else 30.0 * (flow_r ** 3))
            ct_fan_kw.append(0.0 if is_any_ac else 20.0 * flow_r)

    total_kw = np.array(comp_kw) + np.array(chw_pri_kw) + np.array(chw_sec_kw) + np.array(cw_pump_kw) + np.array(ct_fan_kw)
    hourly_cost = total_kw * tariffs

    return {
        "op_tr": np.array(op_tr),
        "charge_tr": np.array(charge_tr),
        "discharge_tr": np.array(discharge_tr),
        "loading_pct": np.array(lf_list),
        "comp_kw": np.array(comp_kw),
        "chw_pri_kw": np.array(chw_pri_kw),
        "chw_sec_kw": np.array(chw_sec_kw),
        "cw_pump_kw": np.array(cw_pump_kw),
        "ct_fan_kw": np.array(ct_fan_kw),
        "total_kw": total_kw,
        "hourly_cost": hourly_cost,
        "daily_opex": np.sum(hourly_cost),
        "annual_opex": np.sum(hourly_cost) * 365.0
    }

def simulate_pcm_tes_24h(df_24h: pd.DataFrame, tes_capacity_trh: float, charge_chiller_tr: float, fleet_installed_tr: float):
    """Simulates Dedicated PCM Brine Charge Chiller Dispatch over lowest 8-hour tariff block."""
    hours = df_24h["Hour"].values
    loads = df_24h["Cooling Load (TR)"].values
    tariffs = df_24h["Tariff (₹/kWh)"].values
    
    rolling_8h = [np.sum([tariffs[(i+j)%24] for j in range(8)]) for i in range(24)]
    best_start = np.argmin(rolling_8h)
    charge_hours = [(best_start + j) % 24 for j in range(8)]
    peak_hours_idx = np.argsort(tariffs)[::-1][:6]

    storage_state = 0.0
    op_tr, c_tr, d_tr = [], [], []
    c_kw, b_kw, pri_kw, sec_kw, cw_kw, ct_kw = [], [], [], [], [], []
    lf_list, mode = [], []

    for i in range(24):
        h = hours[i]
        load = loads[i]
        is_charge = (i in charge_hours)
        is_peak = (i in peak_hours_idx)
        
        c_k, b_k = 0.0, 0.0
        c_val, d_val = 0.0, 0.0
        
        if is_charge:
            c_val = charge_chiller_tr
            c_k = charge_chiller_tr * 0.82 # Dedicated Brine Chiller running at sub-zero
            storage_state = min(tes_capacity_trh, storage_state + c_val)
            lf = load / max(1.0, fleet_installed_tr)
            b_k = load * get_chiller_kw_per_tr(lf, base_kw_tr=0.62, is_night=(h >= 22 or h <= 6))
            op_tr_curr = load
            mode.append("CHARGING")
        elif is_peak and storage_state > 0:
            d_val = min(load, storage_state)
            storage_state -= d_val
            rem_load = load - d_val
            op_tr_curr = rem_load
            lf = rem_load / max(1.0, fleet_installed_tr)
            b_k = rem_load * get_chiller_kw_per_tr(lf, base_kw_tr=0.62) if rem_load > 0 else 0.0
            mode.append("FULL DISCHARGE" if rem_load == 0 else "PARTIAL DISCHARGE")
        else:
            op_tr_curr = load
            lf = load / max(1.0, fleet_installed_tr)
            b_k = load * get_chiller_kw_per_tr(lf, base_kw_tr=0.62, is_night=(h >= 22 or h <= 6))
            mode.append("NORMAL")
            
        lf_list.append(lf * 100.0)
        op_tr.append(op_tr_curr)
        c_tr.append(c_val)
        d_tr.append(d_val)
        
        c_kw.append(c_k)
        b_kw.append(b_k)
        pri_kw.append(18.0)
        sec_kw.append(22.0)
        cw_kw.append(25.0)
        ct_kw.append(15.0)

    total_kw = np.array(c_kw) + np.array(b_kw) + np.array(pri_kw) + np.array(sec_kw) + np.array(cw_kw) + np.array(ct_kw)
    hourly_cost = total_kw * tariffs

    return {
        "op_tr": np.array(op_tr),
        "charge_tr": np.array(c_tr),
        "discharge_tr": np.array(d_tr),
        "loading_pct": np.array(lf_list),
        "comp_kw": np.array(c_kw) + np.array(b_kw),
        "chw_pri_kw": np.array(pri_kw),
        "chw_sec_kw": np.array(sec_kw),
        "cw_pump_kw": np.array(cw_kw),
        "ct_fan_kw": np.array(ct_kw),
        "total_kw": total_kw,
        "hourly_cost": hourly_cost,
        "daily_opex": np.sum(hourly_cost),
        "annual_opex": np.sum(hourly_cost) * 365.0,
        "mode": mode,
        "charge_start_hour": charge_hours[0] + 1
    }

def simulate_stratified_tes_24h(df_24h: pd.DataFrame, tes_capacity_trh: float, fleet_installed_tr: float):
    """Simulates Stratified TES bounded by available spare chiller capacity (Available_TR = Fleet - Load)."""
    hours = df_24h["Hour"].values
    loads = df_24h["Cooling Load (TR)"].values
    tariffs = df_24h["Tariff (₹/kWh)"].values
    
    low_tariff_thresh = np.percentile(tariffs, 40)
    peak_tariff_thresh = np.percentile(tariffs, 75)
    
    storage_state = 0.0
    op_tr, c_tr, d_tr = [], [], []
    comp_kw, pri_kw, sec_kw, cw_kw, ct_kw = [], [], [], [], []
    lf_list, mode = [], []

    for i in range(24):
        h = hours[i]
        load = loads[i]
        t = tariffs[i]
        
        avail_tr = max(0.0, fleet_installed_tr - load)
        c_val, d_val = 0.0, 0.0
        
        if t <= low_tariff_thresh and avail_tr > 100:
            c_val = min(avail_tr, (tes_capacity_trh - storage_state) / 2.0)
            storage_state = min(tes_capacity_trh, storage_state + c_val)
            total_chiller_tr = load + c_val
            op_tr_curr = total_chiller_tr
            lf = total_chiller_tr / max(1.0, fleet_installed_tr)
            c_k = total_chiller_tr * get_chiller_kw_per_tr(lf, base_kw_tr=0.62, is_night=(h >= 22 or h <= 6))
            mode.append("CHARGING")
        elif t >= peak_tariff_thresh and storage_state > 0:
            d_val = min(load, storage_state)
            storage_state -= d_val
            rem_load = load - d_val
            op_tr_curr = rem_load
            lf = rem_load / max(1.0, fleet_installed_tr)
            c_k = rem_load * get_chiller_kw_per_tr(lf, base_kw_tr=0.62) if rem_load > 0 else 0.0
            mode.append("FULL DISCHARGE" if rem_load == 0 else "PARTIAL DISCHARGE")
        else:
            op_tr_curr = load
            lf = load / max(1.0, fleet_installed_tr)
            c_k = load * get_chiller_kw_per_tr(lf, base_kw_tr=0.62, is_night=(h >= 22 or h <= 6))
            mode.append("NORMAL")
            
        lf_list.append(lf * 100.0)
        op_tr.append(op_tr_curr)
        c_tr.append(c_val)
        d_tr.append(d_val)
        
        comp_kw.append(c_k)
        pri_kw.append(20.0)
        sec_kw.append(20.0)
        cw_kw.append(22.0)
        ct_kw.append(14.0)

    total_kw = np.array(comp_kw) + np.array(pri_kw) + np.array(sec_kw) + np.array(cw_kw) + np.array(ct_kw)
    hourly_cost = total_kw * tariffs

    return {
        "op_tr": np.array(op_tr),
        "charge_tr": np.array(c_tr),
        "discharge_tr": np.array(d_tr),
        "loading_pct": np.array(lf_list),
        "comp_kw": np.array(comp_kw),
        "chw_pri_kw": np.array(pri_kw),
        "chw_sec_kw": np.array(sec_kw),
        "cw_pump_kw": np.array(cw_kw),
        "ct_fan_kw": np.array(ct_kw),
        "total_kw": total_kw,
        "hourly_cost": hourly_cost,
        "daily_opex": np.sum(hourly_cost),
        "annual_opex": np.sum(hourly_cost) * 365.0,
        "mode": mode
    }