"""
Cooling Energy Transition Platform (CETP) - Physics & Dual-Benefit Engine
File: physics_engine.py
"""
import numpy as np
import urllib.request
import json

def expand_24_to_8760(arr_24: np.ndarray) -> np.ndarray:
    return np.tile(arr_24, 365)

def fetch_live_weather_wbt(lat: float = 28.4595, lon: float = 77.0266) -> dict:
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,relative_humidity_2m&forecast_days=1"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=3) as response:
            data = json.loads(response.read().decode())
            return {"dbt": data["hourly"]["temperature_2m"][:24], "status": "LIVE"}
    except Exception:
        return {"dbt": [28.0 + 8.0 * np.sin((h - 8) * np.pi / 12) for h in range(24)], "status": "FALLBACK"}

def calc_tr(flow_m3h, dt_c, fluid="water"):
    """Calculates TR dynamically from flow and delta T."""
    cp = 4.186 if fluid == "water" else 3.65
    rho = 1000.0 if fluid == "water" else 1035.0
    return max(0.0, ((flow_m3h * rho / 3600.0) * cp * dt_c) / 3.51685)

def calc_pump_kw(flow_m3h, head_m, eff=0.75):
    """Calculates hydraulic pump power."""
    return max(0.0, (9.81 * (flow_m3h * 1000.0 / 3600.0) * head_m) / (eff * 1000.0))

def get_design_pump_kw(fleet_tr, is_cw=False):
    """Dynamically sizes Greenfield/Restored design pumps based on TR."""
    dt_c = 5.0 if is_cw else 7.0 # 5°C CW Delta T, 7°C CHW Delta T
    flow_m3h = (fleet_tr * 3.51685 * 3600.0) / (4.186 * 1000.0 * dt_c)
    head_m = 25.0 if is_cw else 30.0
    return calc_pump_kw(flow_m3h, head_m)

def get_fleet_ikw(fleet_df):
    """Extracts actual ikW/TR input from the Chiller Fleet editor."""
    if fleet_df.empty or "ikW/TR" not in fleet_df.columns: return 0.62
    weights = fleet_df["Capacity (TR)"] * fleet_df["Quantity"]
    if sum(weights) == 0: return 0.62
    return np.average(fleet_df["ikW/TR"], weights=weights)

def get_plv_kw_tr(load_factor, base_kw_tr=0.62, is_air_cooled=False, is_brine=False, is_night=False):
    """Applies ASHRAE part-load degradation and ambient/air-cooled penalties."""
    if load_factor <= 0: return 0.0
    base = 0.85 if is_brine else base_kw_tr
    
    # Air-cooled chillers draw significantly more power
    if is_air_cooled and not is_brine:
        base *= 1.35 
        
    if load_factor < 0.3: plv = 1.25
    elif load_factor < 0.5: plv = 1.10
    elif load_factor < 0.85: plv = 0.95
    else: plv = 1.00
    
    return base * plv * (0.92 if is_night else 1.00)

def simulate_conventional(load_24, tar_24, fleet_tr, scope, audit_cfg: dict, fleet_df, running_days):
    """
    BASELINE SIMULATION: 
    If Brownfield, locks in the highly-inefficient audited state for accurate payback measurement.
    If Greenfield, runs an optimized N+1 conventional plant.
    """
    comp, chw, cw, ct, charge, discharge = [], [], [], [], [], []
    fleet_ikw = get_fleet_ikw(fleet_df)
    is_any_ac = any("Air-Cooled" in str(t) for t in fleet_df["Chiller Type"]) if not fleet_df.empty else False
    
    # Greenfield Design Pump Values
    des_chw_kw = get_design_pump_kw(fleet_tr, is_cw=False)
    des_cw_kw = get_design_pump_kw(fleet_tr, is_cw=True)
    des_ct_kw = 25.0 * (fleet_tr / 1000.0) # Scaling CT fan by TR

    if scope == "Brownfield (Retrofit)":
        kw_chw = calc_pump_kw(audit_cfg.get("run_chw_flow_m3h", 500.0), audit_cfg.get("run_chw_head_m", 30.0))
        kw_cw = 0.0 if is_any_ac else calc_pump_kw(audit_cfg.get("run_cw_flow_m3h", 600.0), audit_cfg.get("run_cw_head_m", 25.0))
        kw_ct = 0.0 if is_any_ac else audit_cfg.get("run_ct_fan_kw", 45.0)

    for h, tr in enumerate(load_24):
        charge.append(0.0); discharge.append(0.0)
        
        if scope == "Brownfield (Retrofit)":
            # Inefficient Constant Speed Profile
            comp.append(tr * fleet_ikw) 
            chw.append(kw_chw); cw.append(kw_cw); ct.append(kw_ct)
        else:
            # Greenfield VFD Profile
            lf = min(1.0, tr / max(1.0, fleet_tr))
            flow_ratio = max(0.4, lf)
            comp.append(tr * get_plv_kw_tr(lf, fleet_ikw, is_any_ac, False, (h>=22 or h<=6)))
            chw.append(des_chw_kw * (flow_ratio ** 3))
            cw.append(0.0 if is_any_ac else des_cw_kw * (flow_ratio ** 3))
            ct.append(0.0 if is_any_ac else des_ct_kw * flow_ratio)
            
    tot_kw = np.array(comp) + np.array(chw) + np.array(cw) + np.array(ct)
    return {"cooling_tr": load_24, "charge_tr": charge, "discharge_tr": discharge, "comp_kw": comp, "chw_pump_kw": chw, "cw_pump_kw": cw, "ct_fan_kw": ct, "total_kw": tot_kw, "tariff": tar_24, "hourly_cost": tot_kw * tar_24, "annual_opex": np.sum(tot_kw * tar_24) * running_days}

def simulate_pcm(load_24, tar_24, fleet_tr, tes_trh, charge_chiller_tr, fleet_df, running_days):
    """
    PCM TES SIMULATION:
    Always assumes THERMODYNAMIC RESTORATION. Base plant is fixed to optimal VFD design.
    """
    comp, chw, cw, ct, charge, discharge = [], [], [], [], [], []
    storage = 0.0
    fleet_ikw = get_fleet_ikw(fleet_df)
    is_any_ac = any("Air-Cooled" in str(t) for t in fleet_df["Chiller Type"]) if not fleet_df.empty else False
    
    des_chw_kw = get_design_pump_kw(fleet_tr, is_cw=False)
    des_cw_kw = get_design_pump_kw(fleet_tr, is_cw=True)
    des_ct_kw = 25.0 * (fleet_tr / 1000.0)

    rolling_8 = [sum(tar_24[(i+j)%24] for j in range(8)) for i in range(24)]
    charge_hrs = [(np.argmin(rolling_8) + j)%24 for j in range(8)]
    peak_hrs = np.argsort(tar_24)[::-1][:6]
    
    for h, tr in enumerate(load_24):
        c_k, chw_k, cw_k, ct_k, c_tr, d_tr = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
        is_night = (h >= 22 or h <= 6)
        
        if h in charge_hrs:
            c_tr = charge_chiller_tr
            c_k += charge_chiller_tr * get_plv_kw_tr(1.0, 0.85, False, True, True) # Brine Chiller
            storage = min(tes_trh, storage + c_tr)
            
            lf = tr / max(1.0, fleet_tr)
            c_k += tr * get_plv_kw_tr(lf, fleet_ikw, is_any_ac, False, is_night)
            
            chw_k = (des_chw_kw * (max(0.4, lf)**3)) + (get_design_pump_kw(charge_chiller_tr, False)) # Facility + Brine Pump
            cw_k = 0.0 if is_any_ac else (des_cw_kw * (max(0.4, lf)**3)) + (get_design_pump_kw(charge_chiller_tr, True))
            ct_k = 0.0 if is_any_ac else (des_ct_kw * max(0.4, lf)) + 15.0
            
        elif h in peak_hrs and storage > 0:
            d_tr = min(tr, storage)
            storage -= d_tr
            rem = tr - d_tr
            if rem > 0:
                lf = rem / max(1.0, fleet_tr)
                c_k += rem * get_plv_kw_tr(lf, fleet_ikw, is_any_ac, False, False)
                chw_k = des_chw_kw * (max(0.4, lf)**3)
                cw_k = 0.0 if is_any_ac else des_cw_kw * (max(0.4, lf)**3)
                ct_k = 0.0 if is_any_ac else des_ct_kw * max(0.4, lf)
            else:
                chw_k = des_chw_kw * 0.4 # Minimum flow secondary pumps ONLY
                cw_k, ct_k = 0.0, 0.0
        else:
            lf = tr / max(1.0, fleet_tr)
            c_k += tr * get_plv_kw_tr(lf, fleet_ikw, is_any_ac, False, is_night)
            chw_k = des_chw_kw * (max(0.4, lf)**3)
            cw_k = 0.0 if is_any_ac else des_cw_kw * (max(0.4, lf)**3)
            ct_k = 0.0 if is_any_ac else des_ct_kw * max(0.4, lf)
            
        charge.append(c_tr); discharge.append(d_tr)
        comp.append(c_k); chw.append(chw_k); cw.append(cw_k); ct.append(ct_k)
        
    tot_kw = np.array(comp) + np.array(chw) + np.array(cw) + np.array(ct)
    return {"cooling_tr": load_24, "charge_tr": charge, "discharge_tr": discharge, "comp_kw": comp, "chw_pump_kw": chw, "cw_pump_kw": cw, "ct_fan_kw": ct, "total_kw": tot_kw, "tariff": tar_24, "hourly_cost": tot_kw * tar_24, "annual_opex": np.sum(tot_kw * tar_24) * running_days}

def simulate_stratified(load_24, tar_24, fleet_tr, tes_trh, fleet_df, running_days):
    """
    STRATIFIED TES SIMULATION:
    Always assumes THERMODYNAMIC RESTORATION. Bounds charging by Available Spare Chiller Capacity.
    """
    comp, chw, cw, ct, charge, discharge = [], [], [], [], [], []
    storage = 0.0
    fleet_ikw = get_fleet_ikw(fleet_df)
    is_any_ac = any("Air-Cooled" in str(t) for t in fleet_df["Chiller Type"]) if not fleet_df.empty else False
    
    des_chw_kw = get_design_pump_kw(fleet_tr, is_cw=False)
    des_cw_kw = get_design_pump_kw(fleet_tr, is_cw=True)
    des_ct_kw = 25.0 * (fleet_tr / 1000.0)
    
    low_tar, peak_tar = np.percentile(tar_24, 40), np.percentile(tar_24, 75)
    
    for h, tr in enumerate(load_24):
        c_k, chw_k, cw_k, ct_k, c_tr, d_tr = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
        spare = max(0.0, fleet_tr - tr)
        is_night = (h >= 22 or h <= 6)
        
        if tar_24[h] <= low_tar and spare > 50:
            c_tr = min(spare, (tes_trh - storage)/2.0)
            storage = min(tes_trh, storage + c_tr)
            lf = (tr + c_tr) / max(1.0, fleet_tr)
            c_k = (tr + c_tr) * get_plv_kw_tr(lf, fleet_ikw, is_any_ac, False, is_night)
            
            chw_k = des_chw_kw * (max(0.4, lf)**3)
            cw_k = 0.0 if is_any_ac else des_cw_kw * (max(0.4, lf)**3)
            ct_k = 0.0 if is_any_ac else des_ct_kw * max(0.4, lf)
            
        elif tar_24[h] >= peak_tar and storage > 0:
            d_tr = min(tr, storage)
            storage -= d_tr
            rem = tr - d_tr
            if rem > 0:
                lf = rem / max(1.0, fleet_tr)
                c_k = rem * get_plv_kw_tr(lf, fleet_ikw, is_any_ac, False, False)
                chw_k = des_chw_kw * (max(0.4, lf)**3)
                cw_k = 0.0 if is_any_ac else des_cw_kw * (max(0.4, lf)**3)
                ct_k = 0.0 if is_any_ac else des_ct_kw * max(0.4, lf)
            else:
                chw_k = des_chw_kw * 0.4
                cw_k, ct_k = 0.0, 0.0
        else:
            lf = tr / max(1.0, fleet_tr)
            c_k = tr * get_plv_kw_tr(lf, fleet_ikw, is_any_ac, False, is_night)
            chw_k = des_chw_kw * (max(0.4, lf)**3)
            cw_k = 0.0 if is_any_ac else des_cw_kw * (max(0.4, lf)**3)
            ct_k = 0.0 if is_any_ac else des_ct_kw * max(0.4, lf)
            
        charge.append(c_tr); discharge.append(d_tr)
        comp.append(c_k); chw.append(chw_k); cw.append(cw_k); ct.append(ct_k)
        
    tot_kw = np.array(comp) + np.array(chw) + np.array(cw) + np.array(ct)
    return {"cooling_tr": load_24, "charge_tr": charge, "discharge_tr": discharge, "comp_kw": comp, "chw_pump_kw": chw, "cw_pump_kw": cw, "ct_fan_kw": ct, "total_kw": tot_kw, "tariff": tar_24, "hourly_cost": tot_kw * tar_24, "annual_opex": np.sum(tot_kw * tar_24) * running_days}