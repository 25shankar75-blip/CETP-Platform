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
        safe_loc = urllib.parse.quote(location_str)
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={safe_loc}&count=1"
        geo_req = urllib.request.Request(geo_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(geo_req, timeout=3) as geo_resp:
            geo_data = json.loads(geo_resp.read().decode())
            if "results" in geo_data and len(geo_data["results"]) > 0:
                lat, lon = geo_data["results"][0]["latitude"], geo_data["results"][0]["longitude"]
            else:
                lat, lon = 28.4595, 77.0266  

        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,relative_humidity_2m&forecast_days=1"
        w_req = urllib.request.Request(weather_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(w_req, timeout=3) as w_resp:
            w_data = json.loads(w_resp.read().decode())
            dbt = w_data["hourly"]["temperature_2m"][:24]
            rh = w_data["hourly"]["relative_humidity_2m"][:24]
            wbt = [
                d * np.arctan(0.151977 * (r + 8.313659)**0.5) + np.arctan(d + r) - np.arctan(r - 1.676331) + 0.00391838 * (r**1.5) * np.arctan(0.023101 * r) - 4.686035 
                for d, r in zip(dbt, rh)
            ]
            return {"wbt": wbt, "dbt": dbt, "status": "LIVE"}
    except Exception:
        dbt_syn = [28.0 + 8.0 * np.sin((h - 8) * np.pi / 12) for h in range(24)]
        wbt_syn = [22.0 + 5.0 * np.sin((h - 8) * np.pi / 12) for h in range(24)]
        return {"wbt": wbt_syn, "dbt": dbt_syn, "status": "FALLBACK"}

def calc_design_flow(tr, dt_c, fluid="water"):
    if dt_c <= 0: return 0.0
    cp = 4.186 if fluid == "water" else 3.65
    rho = 1000.0 if fluid == "water" else 1035.0
    return (tr * 3.51685 * 3600.0) / (cp * dt_c * rho)

def calc_pump_kw(flow_m3h, head_m, eff=0.75):
    if flow_m3h <= 0 or head_m <= 0: return 0.0
    return max(0.0, (9.81 * (flow_m3h * 1000.0 / 3600.0) * head_m) / (eff * 1000.0))

def get_fleet_ikw(fleet_df):
    if fleet_df.empty or "ikW/TR" not in fleet_df.columns: return 0.62
    active_df = fleet_df[fleet_df["Standby"] == False] if "Standby" in fleet_df.columns else fleet_df
    if active_df.empty: active_df = fleet_df
    weights = active_df["Capacity (TR)"] * active_df["Quantity"]
    if sum(weights) == 0: return 0.62
    return np.average(active_df["ikW/TR"], weights=weights)

def check_fleet_air_cooled(fleet_df):
    if fleet_df.empty or "Chiller Type" not in fleet_df.columns: return False
    return any("Air-Cooled" in str(t) for t in fleet_df["Chiller Type"])

def get_plv_kw_tr(load_factor, base_kw_tr=0.62, is_air_cooled=False, is_brine=False, wbt_val=24.0):
    if load_factor <= 0: return 0.0
    base = 0.85 if is_brine else base_kw_tr
    if is_air_cooled and not is_brine: base *= 1.35 
    if load_factor < 0.3: plv = 1.25
    elif load_factor < 0.5: plv = 1.10
    elif load_factor < 0.85: plv = 0.95
    else: plv = 1.00
    weather_relief = max(0.80, min(1.15, 1.0 - ((24.0 - wbt_val) * 0.015)))
    return base * plv * weather_relief

def calc_water_consumption_m3(cooling_tr_array, is_air_cooled=False, running_days=365):
    if is_air_cooled: return 0.0
    return ((np.sum(cooling_tr_array) * 16.0) / 1000.0) * running_days

def determine_design_kws(fleet_tr, scope, audit_cfg, is_ac):
    if scope == "Brownfield (Retrofit)":
        p_kw = calc_pump_kw(audit_cfg.get("run_chw_flow_m3h", 0.0), audit_cfg.get("run_chw_head_m", 30.0))
        s_kw = calc_pump_kw(audit_cfg.get("run_sec_chw_flow_m3h", 0.0), audit_cfg.get("run_sec_chw_head_m", 0.0))
        cw_kw = 0.0 if is_ac else calc_pump_kw(audit_cfg.get("run_cw_flow_m3h", 0.0), audit_cfg.get("run_cw_head_m", 25.0))
        ct_kw = 0.0 if is_ac else audit_cfg.get("run_ct_fan_kw", 0.0)
    else:
        dt_chw = max(1.0, audit_cfg.get("run_chw_ret_c", 12.0) - audit_cfg.get("run_chw_sup_c", 8.0))
        flow_chw = calc_design_flow(fleet_tr, dt_chw)
        p_kw = calc_pump_kw(flow_chw, audit_cfg.get("run_chw_head_m", 30.0))
        s_kw = calc_pump_kw(flow_chw, audit_cfg.get("run_sec_chw_head_m", 0.0))
        dt_cw = max(1.0, audit_cfg.get("run_cw_ret_c", 37.0) - audit_cfg.get("run_cw_sup_c", 32.0))
        flow_cw = calc_design_flow(fleet_tr * 1.25, dt_cw)
        cw_kw = 0.0 if is_ac else calc_pump_kw(flow_cw, audit_cfg.get("run_cw_head_m", 25.0))
        ct_kw = 0.0 if is_ac else (25.0 * (fleet_tr / 1000.0))
    return p_kw, s_kw, cw_kw, ct_kw

def simulate_conventional(load_24, tar_24, wbt_24, fleet_tr, scope, audit_cfg, fleet_df, running_days):
    comp, chw_pri, chw_sec, cw, ct, charge, discharge, op_chiller_tr, loading_factor = [], [], [], [], [], [], [], [], []
    fleet_ikw = get_fleet_ikw(fleet_df)
    is_ac = check_fleet_air_cooled(fleet_df)
    des_chw_p_kw, des_chw_s_kw, des_cw_kw, des_ct_kw = determine_design_kws(fleet_tr, scope, audit_cfg, is_ac)

    for h, tr in enumerate(load_24):
        charge.append(0.0); discharge.append(0.0); op_chiller_tr.append(tr)
        lf = min(1.0, tr / max(1.0, fleet_tr))
        loading_factor.append(lf * 100.0)
        pump_lf = max(0.30, lf) 
        
        if scope == "Brownfield (Retrofit)":
            comp.append(tr * fleet_ikw) 
            chw_pri.append(des_chw_p_kw); chw_sec.append(des_chw_s_kw); cw.append(des_cw_kw); ct.append(des_ct_kw)
        else:
            comp.append(tr * get_plv_kw_tr(lf, fleet_ikw, is_ac, False, wbt_24[h]))
            chw_pri.append(des_chw_p_kw * (pump_lf**3))
            chw_sec.append(des_chw_s_kw * (pump_lf**3)) 
            cw.append(des_cw_kw * (pump_lf**3))
            ct.append(des_ct_kw * pump_lf)
            
    tot_kw = np.array(comp) + np.array(chw_pri) + np.array(chw_sec) + np.array(cw) + np.array(ct)
    water_m3 = calc_water_consumption_m3(np.array(op_chiller_tr), is_air_cooled=is_ac, running_days=running_days)
    
    return {
        "cooling_tr": load_24, "charge_tr": charge, "discharge_tr": discharge, "op_chiller_tr": op_chiller_tr,
        "loading_factor": loading_factor, "comp_kw": comp, "chw_pri_kw": chw_pri, "chw_sec_kw": chw_sec,
        "cw_pump_kw": cw, "ct_fan_kw": ct, "total_kw": tot_kw, "tariff": tar_24, "hourly_cost": tot_kw * tar_24,
        "annual_opex": np.sum(tot_kw * tar_24) * running_days, "water_m3": water_m3
    }

def simulate_pcm(load_24, tar_24, wbt_24, base_chiller_tr, tes_trh, charge_chiller_tr, fleet_df, audit_cfg, running_days, scope):
    comp, chw_pri, chw_sec, cw, ct, charge, discharge, op_chiller_tr, loading_factor = [], [], [], [], [], [], [], [], []
    fleet_ikw = get_fleet_ikw(fleet_df)
    is_ac = check_fleet_air_cooled(fleet_df)
    des_chw_p_kw, des_chw_s_kw, des_cw_kw, des_ct_kw = determine_design_kws(base_chiller_tr, scope, audit_cfg, is_ac)

    # 1. Predictive BMS: Identify Charging Window
    rolling_8 = [sum(tar_24[(i+j)%24] for j in range(8)) for i in range(24)]
    charge_hrs = [(np.argmin(rolling_8) + j)%24 for j in range(8)]
    
    # 2. Predictive BMS: Global Lookahead Discharge Schedule
    discharge_schedule = [0.0] * 24
    storage_avail = tes_trh
    non_charge_hrs = [h for h in range(24) if h not in charge_hrs]
    sorted_discharge_hrs = sorted(non_charge_hrs, key=lambda h: (tar_24[h], load_24[h]), reverse=True)
    
    for h in sorted_discharge_hrs:
        if storage_avail <= 0: break
        alloc = min(load_24[h], storage_avail)
        discharge_schedule[h] = alloc
        storage_avail -= alloc

    storage = 0.0
    for h, tr in enumerate(load_24):
        c_k, chw_p_k, chw_s_k, cw_k, ct_k, c_tr, d_tr, op_tr_curr = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, tr
        
        if h in charge_hrs:
            c_tr = charge_chiller_tr
            c_k += charge_chiller_tr * get_plv_kw_tr(1.0, 0.85, False, True, wbt_24[h])
            storage = min(tes_trh, storage + c_tr)
            
            op_tr_curr = tr
            lf = tr / max(1.0, base_chiller_tr)
            pump_lf = max(0.30, lf)
            c_k += tr * get_plv_kw_tr(lf, fleet_ikw, is_ac, False, wbt_24[h])
            
            chw_p_k = des_chw_p_kw * (pump_lf**3)
            chw_s_k = (des_chw_s_kw * (pump_lf**3)) + calc_pump_kw(calc_design_flow(charge_chiller_tr, 5.0, "brine"), 30.0) 
            cw_k = 0.0 if is_ac else (des_cw_kw * (pump_lf**3)) + calc_pump_kw(calc_design_flow(charge_chiller_tr*1.2, 5.0), 25.0)
            ct_k = 0.0 if is_ac else (des_ct_kw * pump_lf) + 15.0
            
        else:
            d_tr = discharge_schedule[h]
            actual_discharge = min(d_tr, storage)
            storage -= actual_discharge
            op_tr_curr = max(0.0, tr - actual_discharge)
            
            if op_tr_curr > 0:
                lf = op_tr_curr / max(1.0, base_chiller_tr)
                pump_lf = max(0.30, lf)
                c_k += op_tr_curr * get_plv_kw_tr(lf, fleet_ikw, is_ac, False, wbt_24[h])
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
    water_m3 = calc_water_consumption_m3(np.array(op_chiller_tr) + np.array(charge), is_air_cooled=is_ac, running_days=running_days)
    
    return {
        "cooling_tr": load_24, "charge_tr": charge, "discharge_tr": discharge, "op_chiller_tr": op_chiller_tr,
        "loading_factor": loading_factor, "comp_kw": comp, "chw_pri_kw": chw_pri, "chw_sec_kw": chw_sec,
        "cw_pump_kw": cw, "ct_fan_kw": ct, "total_kw": tot_kw, "tariff": tar_24, "hourly_cost": tot_kw * tar_24,
        "annual_opex": np.sum(tot_kw * tar_24) * running_days, "water_m3": water_m3
    }

def simulate_stratified(load_24, tar_24, wbt_24, base_chiller_tr, tes_trh, fleet_df, audit_cfg, running_days, scope):
    comp, chw_pri, chw_sec, cw, ct, charge, discharge, op_chiller_tr, loading_factor = [], [], [], [], [], [], [], [], []
    fleet_ikw = get_fleet_ikw(fleet_df)
    is_ac = check_fleet_air_cooled(fleet_df)
    des_chw_p_kw, des_chw_s_kw, des_cw_kw, des_ct_kw = determine_design_kws(base_chiller_tr, scope, audit_cfg, is_ac)
    
    # 1. Predictive BMS: Identify Charging Window
    low_tar = np.percentile(tar_24, 35) # Bottom ~8 hours
    charge_hrs = [h for h in range(24) if tar_24[h] <= low_tar]
    
    # 2. Predictive BMS: Calculate Max Possible Charge given Spare Capacity
    total_charge_potential = sum(max(0.0, base_chiller_tr - load_24[h]) for h in charge_hrs)
    actual_max_storage = min(tes_trh, total_charge_potential)
    
    # 3. Predictive BMS: Global Lookahead Discharge Schedule
    discharge_schedule = [0.0] * 24
    storage_avail = actual_max_storage
    non_charge_hrs = [h for h in range(24) if h not in charge_hrs]
    sorted_discharge_hrs = sorted(non_charge_hrs, key=lambda h: (tar_24[h], load_24[h]), reverse=True)
    
    for h in sorted_discharge_hrs:
        if storage_avail <= 0: break
        alloc = min(load_24[h], storage_avail)
        discharge_schedule[h] = alloc
        storage_avail -= alloc

    storage = 0.0
    for h, tr in enumerate(load_24):
        c_k, chw_p_k, chw_s_k, cw_k, ct_k, c_tr, d_tr, op_tr_curr = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, tr
        
        if h in charge_hrs:
            spare = max(0.0, base_chiller_tr - tr)
            c_tr = min(spare, (tes_trh - storage))
            storage = min(tes_trh, storage + c_tr)
            
            op_tr_curr = tr + c_tr
            lf = op_tr_curr / max(1.0, base_chiller_tr)
            pump_lf = max(0.30, lf)
            c_k = op_tr_curr * get_plv_kw_tr(lf, fleet_ikw, is_ac, False, wbt_24[h])
            chw_p_k = des_chw_p_kw * (pump_lf**3)
            chw_s_k = des_chw_s_kw * (pump_lf**3)
            cw_k = 0.0 if is_ac else des_cw_kw * (pump_lf**3)
            ct_k = 0.0 if is_ac else des_ct_kw * pump_lf
            
        else:
            d_tr = discharge_schedule[h]
            actual_discharge = min(d_tr, storage)
            storage -= actual_discharge
            op_tr_curr = max(0.0, tr - actual_discharge)
            
            if op_tr_curr > 0:
                lf = op_tr_curr / max(1.0, base_chiller_tr)
                pump_lf = max(0.30, lf)
                c_k = op_tr_curr * get_plv_kw_tr(lf, fleet_ikw, is_ac, False, wbt_24[h])
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
    water_m3 = calc_water_consumption_m3(np.array(op_chiller_tr), is_air_cooled=is_ac, running_days=running_days)
    
    return {
        "cooling_tr": load_24, "charge_tr": charge, "discharge_tr": discharge, "op_chiller_tr": op_chiller_tr,
        "loading_factor": loading_factor, "comp_kw": comp, "chw_pri_kw": chw_pri, "chw_sec_kw": chw_sec,
        "cw_pump_kw": cw, "ct_fan_kw": ct, "total_kw": tot_kw, "tariff": tar_24, "hourly_cost": tot_kw * tar_24,
        "annual_opex": np.sum(tot_kw * tar_24) * running_days, "water_m3": water_m3
    }