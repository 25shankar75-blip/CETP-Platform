"""
Cooling Energy Transition Platform (CETP) - Physics & Live Weather Engine
File: physics_engine.py
"""
import numpy as np
import urllib.request
import urllib.parse
import json

def expand_24_to_8760(arr_24: np.ndarray) -> np.ndarray:
    return np.tile(arr_24, 365)

def fetch_live_weather_wbt(location_str: str) -> dict:
    """Geocodes location input and fetches Live Open-Meteo WBT and DBT."""
    try:
        safe_loc = urllib.parse.quote(location_str)
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={safe_loc}&count=1"
        geo_req = urllib.request.Request(geo_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(geo_req, timeout=3) as geo_resp:
            geo_data = json.loads(geo_resp.read().decode())
            if "results" in geo_data and len(geo_data["results"]) > 0:
                lat, lon = geo_data["results"][0]["latitude"], geo_data["results"][0]["longitude"]
            else:
                lat, lon = 28.4595, 77.0266  # Fallback Gurugram

        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,relative_humidity_2m&forecast_days=1"
        w_req = urllib.request.Request(weather_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(w_req, timeout=3) as w_resp:
            w_data = json.loads(w_resp.read().decode())
            dbt = w_data["hourly"]["temperature_2m"][:24]
            rh = w_data["hourly"]["relative_humidity_2m"][:24]
            # Stull WBT Approximation for cooling tower efficiency
            wbt = [
                d * np.arctan(0.151977 * (r + 8.313659)**0.5) + np.arctan(d + r) - np.arctan(r - 1.676331) + 0.00391838 * (r**1.5) * np.arctan(0.023101 * r) - 4.686035 
                for d, r in zip(dbt, rh)
            ]
            return {"wbt": wbt, "dbt": dbt, "status": "LIVE"}
    except Exception:
        dbt_syn = [28.0 + 8.0 * np.sin((h - 8) * np.pi / 12) for h in range(24)]
        wbt_syn = [22.0 + 5.0 * np.sin((h - 8) * np.pi / 12) for h in range(24)]
        return {"wbt": wbt_syn, "dbt": dbt_syn, "status": "FALLBACK"}

def calc_tr(flow_m3h, dt_c, fluid="water"):
    cp = 4.186 if fluid == "water" else 3.65
    rho = 1000.0 if fluid == "water" else 1035.0
    return max(0.0, ((flow_m3h * rho / 3600.0) * cp * dt_c) / 3.51685)

def calc_pump_kw(flow_m3h, head_m, eff=0.75):
    return max(0.0, (9.81 * (flow_m3h * 1000.0 / 3600.0) * head_m) / (eff * 1000.0))

def get_design_pump_kw(fleet_tr, is_cw=False):
    dt_c = 5.0 if is_cw else 7.0 
    flow_m3h = (fleet_tr * 3.51685 * 3600.0) / (4.186 * 1000.0 * dt_c)
    return calc_pump_kw(flow_m3h, 25.0 if is_cw else 30.0)

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
        
    # Dynamic Part Load Curves
    if load_factor < 0.3: plv = 1.25
    elif load_factor < 0.5: plv = 1.10
    elif load_factor < 0.85: plv = 0.95
    else: plv = 1.00
    
    weather_relief = max(0.80, min(1.15, 1.0 - ((24.0 - wbt_val) * 0.015)))
    return base * plv * weather_relief

def calc_water_consumption_m3(cooling_tr_array, is_air_cooled=False, running_days=365):
    if is_air_cooled: return 0.0
    total_trh_day = np.sum(cooling_tr_array)
    water_liters_day = total_trh_day * 16.0
    return (water_liters_day / 1000.0) * running_days

def simulate_conventional(load_24, tar_24, wbt_24, fleet_tr, scope, audit_cfg: dict, fleet_df, running_days):
    comp, chw_pri, chw_sec, cw, ct, charge, discharge, op_chiller_tr, loading_factor = [], [], [], [], [], [], [], [], []
    fleet_ikw = get_fleet_ikw(fleet_df)
    is_ac = check_fleet_air_cooled(fleet_df)
    
    des_chw_kw = get_design_pump_kw(fleet_tr, is_cw=False)
    des_cw_kw = get_design_pump_kw(fleet_tr, is_cw=True)
    des_ct_kw = 25.0 * (fleet_tr / 1000.0)

    if scope == "Brownfield (Retrofit)":
        kw_chw_p = calc_pump_kw(audit_cfg.get("run_chw_flow_m3h", 500.0), audit_cfg.get("run_chw_head_m", 30.0))
        kw_chw_s = kw_chw_p * 0.4
        kw_cw = 0.0 if is_ac else calc_pump_kw(audit_cfg.get("run_cw_flow_m3h", 600.0), audit_cfg.get("run_cw_head_m", 25.0))
        kw_ct = 0.0 if is_ac else audit_cfg.get("run_ct_fan_kw", 45.0)

    for h, tr in enumerate(load_24):
        charge.append(0.0); discharge.append(0.0); op_chiller_tr.append(tr)
        lf = min(1.0, tr / max(1.0, fleet_tr))
        loading_factor.append(lf * 100.0)
        
        if scope == "Brownfield (Retrofit)":
            comp.append(tr * fleet_ikw) 
            chw_pri.append(kw_chw_p); chw_sec.append(kw_chw_s); cw.append(kw_cw); ct.append(kw_ct)
        else:
            flow_ratio = max(0.4, lf)
            comp.append(tr * get_plv_kw_tr(lf, fleet_ikw, is_ac, False, wbt_24[h]))
            chw_pri.append(des_chw_kw * flow_ratio)
            chw_sec.append(des_chw_kw * 0.4 * (flow_ratio ** 3)) # Affinity laws
            cw.append(0.0 if is_ac else des_cw_kw * (flow_ratio ** 3))
            ct.append(0.0 if is_ac else des_ct_kw * flow_ratio)
            
    tot_kw = np.array(comp) + np.array(chw_pri) + np.array(chw_sec) + np.array(cw) + np.array(ct)
    water_m3 = calc_water_consumption_m3(np.array(op_chiller_tr), is_air_cooled=is_ac, running_days=running_days)
    
    return {
        "cooling_tr": load_24, "charge_tr": charge, "discharge_tr": discharge, "op_chiller_tr": op_chiller_tr,
        "loading_factor": loading_factor, "comp_kw": comp, "chw_pri_kw": chw_pri, "chw_sec_kw": chw_sec,
        "cw_pump_kw": cw, "ct_fan_kw": ct, "total_kw": tot_kw, "tariff": tar_24, "hourly_cost": tot_kw * tar_24,
        "annual_opex": np.sum(tot_kw * tar_24) * running_days, "water_m3": water_m3
    }

def simulate_pcm(load_24, tar_24, wbt_24, fleet_tr, tes_trh, charge_chiller_tr, fleet_df, running_days):
    comp, chw_pri, chw_sec, cw, ct, charge, discharge, op_chiller_tr, loading_factor = [], [], [], [], [], [], [], [], []
    storage = 0.0
    fleet_ikw = get_fleet_ikw(fleet_df)
    is_ac = check_fleet_air_cooled(fleet_df)
    
    des_chw_kw = get_design_pump_kw(fleet_tr, is_cw=False)
    des_cw_kw = get_design_pump_kw(fleet_tr, is_cw=True)
    des_ct_kw = 25.0 * (fleet_tr / 1000.0)

    rolling_8 = [sum(tar_24[(i+j)%24] for j in range(8)) for i in range(24)]
    charge_hrs = [(np.argmin(rolling_8) + j)%24 for j in range(8)]
    peak_hrs = np.argsort(tar_24)[::-1][:6]
    
    for h, tr in enumerate(load_24):
        c_k, chw_p_k, chw_s_k, cw_k, ct_k, c_tr, d_tr, op_tr_curr = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, tr
        
        if h in charge_hrs:
            c_tr = charge_chiller_tr
            c_k += charge_chiller_tr * get_plv_kw_tr(1.0, 0.85, False, True, wbt_24[h])
            storage = min(tes_trh, storage + c_tr)
            lf = tr / max(1.0, fleet_tr)
            c_k += tr * get_plv_kw_tr(lf, fleet_ikw, is_ac, False, wbt_24[h])
            chw_p_k = des_chw_kw * max(0.4, lf)
            chw_s_k = (des_chw_kw * 0.4 * (max(0.4, lf)**3)) + (get_design_pump_kw(charge_chiller_tr, False))
            cw_k = 0.0 if is_ac else (des_cw_kw * (max(0.4, lf)**3)) + (get_design_pump_kw(charge_chiller_tr, True))
            ct_k = 0.0 if is_ac else (des_ct_kw * max(0.4, lf)) + 15.0
            op_tr_curr = tr
        elif h in peak_hrs and storage > 0:
            d_tr = min(tr, storage)
            storage -= d_tr
            rem = tr - d_tr
            op_tr_curr = rem
            if rem > 0:
                lf = rem / max(1.0, fleet_tr)
                c_k += rem * get_plv_kw_tr(lf, fleet_ikw, is_ac, False, wbt_24[h])
                chw_p_k = des_chw_kw * max(0.4, lf)
                chw_s_k = des_chw_kw * 0.4 * (max(0.4, lf)**3)
                cw_k = 0.0 if is_ac else des_cw_kw * (max(0.4, lf)**3)
                ct_k = 0.0 if is_ac else des_ct_kw * max(0.4, lf)
            else:
                chw_p_k = 0.0
                chw_s_k = des_chw_kw * 0.2
                cw_k, ct_k = 0.0, 0.0
        else:
            lf = tr / max(1.0, fleet_tr)
            c_k += tr * get_plv_kw_tr(lf, fleet_ikw, is_ac, False, wbt_24[h])
            chw_p_k = des_chw_kw * max(0.4, lf)
            chw_s_k = des_chw_kw * 0.4 * (max(0.4, lf)**3)
            cw_k = 0.0 if is_ac else des_cw_kw * (max(0.4, lf)**3)
            ct_k = 0.0 if is_ac else des_ct_kw * max(0.4, lf)
            op_tr_curr = tr
            
        lf_curr = op_tr_curr / max(1.0, fleet_tr)
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

def simulate_stratified(load_24, tar_24, wbt_24, fleet_tr, tes_trh, fleet_df, running_days):
    comp, chw_pri, chw_sec, cw, ct, charge, discharge, op_chiller_tr, loading_factor = [], [], [], [], [], [], [], [], []
    storage = 0.0
    fleet_ikw = get_fleet_ikw(fleet_df)
    is_ac = check_fleet_air_cooled(fleet_df)
    
    des_chw_kw = get_design_pump_kw(fleet_tr, is_cw=False)
    des_cw_kw = get_design_pump_kw(fleet_tr, is_cw=True)
    des_ct_kw = 25.0 * (fleet_tr / 1000.0)
    
    low_tar, peak_tar = np.percentile(tar_24, 40), np.percentile(tar_24, 75)
    
    for h, tr in enumerate(load_24):
        c_k, chw_p_k, chw_s_k, cw_k, ct_k, c_tr, d_tr, op_tr_curr = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, tr
        spare = max(0.0, fleet_tr - tr)
        
        if tar_24[h] <= low_tar and spare > 50:
            c_tr = min(spare, (tes_trh - storage)/2.0)
            storage = min(tes_trh, storage + c_tr)
            tot_load = tr + c_tr
            op_tr_curr = tot_load
            lf = tot_load / max(1.0, fleet_tr)
            c_k = tot_load * get_plv_kw_tr(lf, fleet_ikw, is_ac, False, wbt_24[h])
            chw_p_k = des_chw_kw * max(0.4, lf)
            chw_s_k = des_chw_kw * 0.4 * (max(0.4, lf)**3)
            cw_k = 0.0 if is_ac else des_cw_kw * (max(0.4, lf)**3)
            ct_k = 0.0 if is_ac else des_ct_kw * max(0.4, lf)
            
        elif tar_24[h] >= peak_tar and storage > 0:
            d_tr = min(tr, storage)
            storage -= d_tr
            rem = tr - d_tr
            op_tr_curr = rem
            if rem > 0:
                lf = rem / max(1.0, fleet_tr)
                c_k = rem * get_plv_kw_tr(lf, fleet_ikw, is_ac, False, wbt_24[h])
                chw_p_k = des_chw_kw * max(0.4, lf)
                chw_s_k = des_chw_kw * 0.4 * (max(0.4, lf)**3)
                cw_k = 0.0 if is_ac else des_cw_kw * (max(0.4, lf)**3)
                ct_k = 0.0 if is_ac else des_ct_kw * max(0.4, lf)
            else:
                chw_p_k = 0.0
                chw_s_k = des_chw_kw * 0.2
                cw_k, ct_k = 0.0, 0.0
        else:
            lf = tr / max(1.0, fleet_tr)
            c_k = tr * get_plv_kw_tr(lf, fleet_ikw, is_ac, False, wbt_24[h])
            chw_p_k = des_chw_kw * max(0.4, lf)
            chw_s_k = des_chw_kw * 0.4 * (max(0.4, lf)**3)
            cw_k = 0.0 if is_ac else des_cw_kw * (max(0.4, lf)**3)
            ct_k = 0.0 if is_ac else des_ct_kw * max(0.4, lf)
            op_tr_curr = tr
            
        lf_curr = op_tr_curr / max(1.0, fleet_tr)
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