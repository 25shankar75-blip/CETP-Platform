"""
Cooling Energy Transition Platform (CETP) - Physics Engine
File: physics_engine.py
"""
import numpy as np
import urllib.request
import urllib.parse
import json

def fetch_live_weather_wbt(location_str: str) -> dict:
    try:
        if not location_str: raise ValueError("Empty location")
        safe_loc = urllib.parse.quote(location_str)
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={safe_loc}&count=1"
        geo_req = urllib.request.Request(geo_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(geo_req, timeout=3) as geo_resp:
            geo_data = json.loads(geo_resp.read().decode())
            if "results" in geo_data and len(geo_data["results"]) > 0:
                lat, lon = geo_data["results"][0]["latitude"], geo_data["results"][0]["longitude"]
            else:
                raise ValueError("Location not found")

        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,relative_humidity_2m&forecast_days=1"
        w_req = urllib.request.Request(weather_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(w_req, timeout=3) as w_resp:
            w_data = json.loads(w_resp.read().decode())
            dbt = w_data["hourly"]["temperature_2m"][:24]
            rh = w_data["hourly"]["relative_humidity_2m"][:24]
            # Stull's Formula for Exact Wet Bulb Temperature
            wbt = [
                d * np.arctan(0.151977 * (r + 8.313659)**0.5) + np.arctan(d + r) - np.arctan(r - 1.676331) + 0.00391838 * (r**1.5) * np.arctan(0.023101 * r) - 4.686035 
                for d, r in zip(dbt, rh)
            ]
            return {"wbt": wbt, "dbt": dbt, "status": "LIVE"}
    except Exception:
        # Fallback Diurnal Curve
        dbt_syn = [28.0 + 8.0 * np.sin((h - 8) * np.pi / 12) for h in range(24)]
        wbt_syn = [22.0 + 5.0 * np.sin((h - 8) * np.pi / 12) for h in range(24)]
        return {"wbt": wbt_syn, "dbt": dbt_syn, "status": "FALLBACK"}

def calc_tr(flow_m3h, dt_c, fluid="water"):
    cp = 4.186 if fluid == "water" else 3.65
    rho = 1000.0 if fluid == "water" else 1035.0
    return max(0.0, ((flow_m3h * rho / 3600.0) * cp * dt_c) / 3.51685)

def calc_design_flow(tr, dt_c, fluid="water"):
    if dt_c <= 0: return 0.0
    cp = 4.186 if fluid == "water" else 3.65
    rho = 1000.0 if fluid == "water" else 1035.0
    return (tr * 3.51685 * 3600.0) / (cp * dt_c * rho)

def calc_pump_kw(flow_m3h, head_m, eff=0.75):
    if flow_m3h <= 0 or head_m <= 0: return 0.0
    return max(0.0, (9.81 * (flow_m3h * 1000.0 / 3600.0) * head_m) / (eff * 1000.0))

def get_fleet_ikw(fleet_df, default_val=0.62):
    if fleet_df is None or fleet_df.empty or "ikW/TR" not in fleet_df.columns: return default_val
    active_df = fleet_df[fleet_df["Standby"] == False] if "Standby" in fleet_df.columns else fleet_df
    if active_df.empty: active_df = fleet_df
    weights = active_df["Capacity (TR)"] * active_df["Quantity"]
    if sum(weights) == 0: return default_val
    return np.average(active_df["ikW/TR"], weights=weights)

def check_fleet_air_cooled(fleet_df):
    if fleet_df is None or fleet_df.empty or "Chiller Type" not in fleet_df.columns: return False
    return any("Air-Cooled" in str(t) for t in fleet_df["Chiller Type"])

def get_plv_kw_tr(load_factor, base_kw_tr, brine_kw_tr, is_air_cooled=False, is_pcm_charging=False, wbt_val=24.0):
    if load_factor <= 0: return 0.0
    
    # REV 19 ENFORCEMENT: PCM Freezes at -5.5C, demanding severe penalty during charge.
    base = brine_kw_tr if is_pcm_charging else base_kw_tr
    
    if is_air_cooled and not is_pcm_charging: base *= 1.35 
    
    # VFD Part Load Profile
    if load_factor < 0.3: plv = 1.25
    elif load_factor < 0.5: plv = 1.10
    elif load_factor < 0.85: plv = 0.95
    else: plv = 1.00
    
    # Condenser Weather Relief based on WBT
    weather_relief = max(0.80, min(1.15, 1.0 - ((24.0 - wbt_val) * 0.015)))
    return base * plv * weather_relief

def calc_water_consumption_m3(cooling_tr_array, is_air_cooled=False, running_days=365):
    if is_air_cooled: return 0.0
    return ((np.sum(cooling_tr_array) * 16.0) / 1000.0) * running_days

def determine_design_kws(fleet_tr, scope, audit_cfg, is_ac):
    if scope == "Brownfield (Retrofit)":
        p_kw = calc_pump_kw(audit_cfg.get("run_chw_flow_m3h", 0.0) or 0.0, audit_cfg.get("run_chw_head_m", 30.0) or 30.0)
        s_kw = calc_pump_kw(audit_cfg.get("run_sec_chw_flow_m3h", 0.0) or 0.0, audit_cfg.get("run_sec_chw_head_m", 0.0) or 0.0)
        cw_kw = 0.0 if is_ac else calc_pump_kw(audit_cfg.get("run_cw_flow_m3h", 0.0) or 0.0, audit_cfg.get("run_cw_head_m", 25.0) or 25.0)
        ct_kw = 0.0 if is_ac else (audit_cfg.get("run_ct_fan_kw", 0.0) or 0.0)
    else:
        dt_chw = max(1.0, (audit_cfg.get("run_chw_ret_c") or 12.0) - (audit_cfg.get("run_chw_sup_c") or 8.0))
        flow_chw = calc_design_flow(fleet_tr, dt_chw)
        p_kw = calc_pump_kw(flow_chw, audit_cfg.get("run_chw_head_m") or 30.0)
        s_kw = calc_pump_kw(flow_chw, audit_cfg.get("run_sec_chw_head_m") or 0.0)
        dt_cw = max(1.0, (audit_cfg.get("run_cw_ret_c") or 37.0) - (audit_cfg.get("run_cw_sup_c") or 32.0))
        flow_cw = calc_design_flow(fleet_tr * 1.25, dt_cw)
        cw_kw = 0.0 if is_ac else calc_pump_kw(flow_cw, audit_cfg.get("run_cw_head_m") or 25.0)
        ct_kw = 0.0 if is_ac else (25.0 * (fleet_tr / 1000.0))
    return p_kw, s_kw, cw_kw, ct_kw

def simulate_conventional(load_24, tar_24, wbt_24, active_working_tr, scope, audit_cfg, fleet_df, running_days):
    comp, chw_pri, chw_sec, cw, ct, charge, discharge, op_chiller_tr, loading_factor = [], [], [], [], [], [], [], [], []
    fleet_ikw = get_fleet_ikw(fleet_df, audit_cfg.get("kw_tr_base") or 0.58)
    is_ac = check_fleet_air_cooled(fleet_df)
    des_chw_p_kw, des_chw_s_kw, des_cw_kw, des_ct_kw = determine_design_kws(active_working_tr, scope, audit_cfg, is_ac)

    for h, tr in enumerate(load_24):
        charge.append(0.0); discharge.append(0.0); op_chiller_tr.append(tr)
        lf = min(1.0, tr / max(1.0, active_working_tr))
        loading_factor.append(lf * 100.0)
        pump_lf = max(0.30, lf) # Absolute 30% / 15Hz VFD Limit
        
        if scope == "Brownfield (Retrofit)":
            comp.append(tr * fleet_ikw) 
            chw_pri.append(des_chw_p_kw); chw_sec.append(des_chw_s_kw); cw.append(des_cw_kw); ct.append(des_ct_kw)
        else:
            comp.append(tr * get_plv_kw_tr(lf, fleet_ikw, fleet_ikw, is_ac, False, wbt_24[h]))
            chw_pri.append(des_chw_p_kw * (pump_lf**3))
            chw_sec.append(des_chw_s_kw * (pump_lf**3)) 
            cw.append(des_cw_kw * (pump_lf**3))
            ct.append(des_ct_kw * pump_lf)
            
    tot_kw = np.array(comp) + np.array(chw_pri) + np.array(chw_sec) + np.array(cw) + np.array(ct)
    water_m3 = calc_water_consumption_m3(np.array(op_chiller_tr), is_air_cooled=is_ac, running_days=running_days)
    
    return {
        "base_chiller_tr": active_working_tr, "cooling_tr": load_24, "charge_tr": charge, "discharge_tr": discharge, 
        "op_chiller_tr": op_chiller_tr, "loading_factor": loading_factor, "comp_kw": comp, "chw_pri_kw": chw_pri, 
        "chw_sec_kw": chw_sec, "cw_pump_kw": cw, "ct_fan_kw": ct, "total_kw": tot_kw, "tariff": tar_24, 
        "hourly_cost": tot_kw * tar_24, "annual_opex": np.sum(tot_kw * tar_24) * running_days, "water_m3": water_m3
    }

def simulate_tes(load_24, tar_24, wbt_24, active_working_tr, tes_trh, fleet_df, audit_cfg, running_days, scope, is_pcm):
    """Unified Waterfall Predictive BMS Solver"""
    comp, chw_pri, chw_sec, cw, ct, charge, discharge, op_chiller_tr, loading_factor = [], [], [], [], [], [], [], [], []
    is_greenfield = scope != "Brownfield (Retrofit)"
    base_kw_tr = get_fleet_ikw(fleet_df, audit_cfg.get("kw_tr_base") or 0.58)
    brine_kw_tr = audit_cfg.get("kw_tr_brine") or 0.85
    is_ac = check_fleet_air_cooled(fleet_df)
    peak_load = max(load_24)

    # 1. Identify 8-hour Charge Window (Lowest Tariffs)
    rolling_8 = [sum(tar_24[(i+j)%24] for j in range(8)) for i in range(24)]
    charge_start_hr = np.argmin(rolling_8)
    charge_hrs = [(charge_start_hr + j)%24 for j in range(8)]
    non_charge_hrs = [h for h in range(24) if h not in charge_hrs]
    
    discharge_schedule = [0.0] * 24
    storage_avail = tes_trh
    
    # 2. THE WATERFALL DISCHARGE ALGORITHM (Tariff First, Load Second)
    # Sort non-charging hours by Tariff (highest first), then by Load (highest first)
    sorted_discharge_hrs = sorted(non_charge_hrs, key=lambda h: (tar_24[h], load_24[h]), reverse=True)
    
    for h in sorted_discharge_hrs:
        if storage_avail <= 0.01: break
        alloc = min(load_24[h], storage_avail)
        discharge_schedule[h] = alloc
        storage_avail -= alloc

    # 3. Dynamic Base Chiller Sizing (Greenfield Peak Shaving)
    if is_greenfield:
        # Base chiller must cover the maximum residual load left AFTER the waterfall discharge
        max_residual = max([load_24[h] - discharge_schedule[h] for h in range(24)])
        # Hard cap: Never shrink the base plant below 30% of peak (to handle baseload and night duty safely)
        base_chiller_tr = max(peak_load * 0.30, max_residual)
    else:
        base_chiller_tr = active_working_tr

    # 4. Stratified Charge Verification (Sensible System Limit)
    if not is_pcm:
        charge_avail = sum(max(0.0, base_chiller_tr - load_24[h]) for h in charge_hrs)
        if charge_avail < sum(discharge_schedule):
            # Base chiller too small to charge the tank at night; expand it
            base_chiller_tr += (sum(discharge_schedule) - charge_avail) / len(charge_hrs)

    total_discharge = sum(discharge_schedule)
    actual_charge_tr = total_discharge / len(charge_hrs) if len(charge_hrs) > 0 else 0.0
    
    if is_pcm:
        charge_schedule = [actual_charge_tr if h in charge_hrs else 0.0 for h in range(24)]
    else:
        charge_potential = [max(0.0, base_chiller_tr - load_24[h]) if h in charge_hrs else 0.0 for h in range(24)]
        total_pot = sum(charge_potential)
        charge_schedule = [total_discharge * (charge_potential[h] / total_pot) if h in charge_hrs and total_pot > 0 else 0.0 for h in range(24)]

    des_chw_p_kw, des_chw_s_kw, des_cw_kw, des_ct_kw = determine_design_kws(base_chiller_tr, scope, audit_cfg, is_ac)

    # 5. Cyclical Boundary Condition
    storage = tes_trh if is_pcm else total_discharge

    # 6. Physical Accounting Simulation
    for h, tr in enumerate(load_24):
        c_k, chw_p_k, chw_s_k, cw_k, ct_k, c_tr, d_tr, op_tr_curr = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, tr
        
        if h in charge_hrs:
            c_tr = charge_schedule[h]
            # APPLY REV 19 -5.5C BRINE PENALTY TO PCM DURING CHARGE
            c_k += c_tr * get_plv_kw_tr(1.0, base_kw_tr, brine_kw_tr, is_ac, is_pcm_charging=is_pcm, wbt_val=wbt_24[h]) 
            storage = min(tes_trh, storage + c_tr)
            
            op_tr_curr = tr if is_pcm else tr + c_tr
            lf = op_tr_curr / max(1.0, base_chiller_tr)
            pump_lf = max(0.30, lf)
            c_k += op_tr_curr * get_plv_kw_tr(lf, base_kw_tr, brine_kw_tr, is_ac, is_pcm_charging=False, wbt_val=wbt_24[h])
            
            chw_p_k = des_chw_p_kw * (pump_lf**3)
            chw_s_k = (des_chw_s_kw * (pump_lf**3)) + (calc_pump_kw(calc_design_flow(actual_charge_tr, 5.0, "brine"), 30.0) if is_pcm else 0)
            cw_k = 0.0 if is_ac else (des_cw_kw * (pump_lf**3)) + (calc_pump_kw(calc_design_flow(actual_charge_tr*1.2, 5.0), 25.0) if is_pcm else 0)
            ct_k = 0.0 if is_ac else (des_ct_kw * pump_lf) + (15.0 if is_pcm else 0)
            
        else:
            d_tr = discharge_schedule[h]
            actual_discharge = min(d_tr, storage)
            storage -= actual_discharge
            op_tr_curr = max(0.0, tr - actual_discharge)
            
            if op_tr_curr > 0:
                lf = op_tr_curr / max(1.0, base_chiller_tr)
                pump_lf = max(0.30, lf)
                c_k += op_tr_curr * get_plv_kw_tr(lf, base_kw_tr, brine_kw_tr, is_ac, is_pcm_charging=False, wbt_val=wbt_24[h])
                chw_p_k = des_chw_p_kw * (pump_lf**3)
                chw_s_k = des_chw_s_kw * (pump_lf**3)
                cw_k = 0.0 if is_ac else des_cw_kw * (pump_lf**3)
                ct_k = 0.0 if is_ac else des_ct_kw * pump_lf
            else:
                chw_p_k = 0.0
                chw_s_k = des_chw_s_kw * (0.30**3)  
                cw_k, ct_k = 0.0, 0.0
                
        lf_curr = op_tr_curr / max(1.0, base_chiller_tr)
        loading_factor.append(lf_curr * 100.0)
        op_chiller_tr.append(op_tr_curr)
        charge.append(c_tr); discharge.append(d_tr)
        comp.append(c_k); chw_pri.append(chw_p_k); chw_sec.append(chw_s_k); cw.append(cw_k); ct.append(ct_k)
        
    tot_kw = np.array(comp) + np.array(chw_pri) + np.array(chw_sec) + np.array(cw) + np.array(ct)
    water_m3 = calc_water_consumption_m3(np.array(op_chiller_tr) + (np.array(charge) if is_pcm else 0), is_air_cooled=is_ac, running_days=running_days)
    
    return {
        "base_chiller_tr": base_chiller_tr, "charge_chiller_tr": actual_charge_tr if is_pcm else 0.0,
        "cooling_tr": load_24, "charge_tr": charge, "discharge_tr": discharge, "op_chiller_tr": op_chiller_tr,
        "loading_factor": loading_factor, "comp_kw": comp, "chw_pri_kw": chw_pri, "chw_sec_kw": chw_sec,
        "cw_pump_kw": cw, "ct_fan_kw": ct, "total_kw": tot_kw, "tariff": tar_24, "hourly_cost": tot_kw * tar_24,
        "annual_opex": np.sum(tot_kw * tar_24) * running_days, "water_m3": water_m3
    }

def simulate_pcm(load_24, tar_24, wbt_24, active_working_tr, tes_trh, fleet_df, audit_cfg, running_days, scope):
    return simulate_tes(load_24, tar_24, wbt_24, active_working_tr, tes_trh, fleet_df, audit_cfg, running_days, scope, is_pcm=True)

def simulate_stratified(load_24, tar_24, wbt_24, active_working_tr, tes_trh, fleet_df, audit_cfg, running_days, scope):
    return simulate_tes(load_24, tar_24, wbt_24, active_working_tr, tes_trh, fleet_df, audit_cfg, running_days, scope, is_pcm=False)