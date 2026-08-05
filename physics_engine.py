# physics_engine.py
import numpy as np
import requests

try:
    import CoolProp.CoolProp as CP
    COOLPROP_AVAILABLE = True
except ImportError:
    COOLPROP_AVAILABLE = False

PLV_LOADS = np.array([0.0, 0.25, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 1.00])
PLV_KW_TR = np.array([0.75, 0.70, 0.64, 0.58, 0.54, 0.51, 0.49, 0.50, 0.53])

def get_plv_kw_tr(load_fraction: float) -> float:
    safe_fraction = max(0.0, min(1.0, load_fraction))
    return float(np.interp(safe_fraction, PLV_LOADS, PLV_KW_TR))

def fetch_8760_wbt(location: str, design_wbt: float, enable_api: bool) -> np.ndarray:
    if not enable_api: return generate_synthetic_wbt(design_wbt)
    try:
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={location}&count=1&format=json"
        geo_res = requests.get(geo_url, timeout=5).json()
        if 'results' not in geo_res: raise ValueError("Location not found")
        lat, lon = geo_res['results'][0]['latitude'], geo_res['results'][0]['longitude']
        
        w_url = f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date=2023-01-01&end_date=2023-12-31&hourly=wet_bulb_temperature_2m"
        w_res = requests.get(w_url, timeout=10).json()
        wbt_data = np.array(w_res['hourly']['wet_bulb_temperature_2m'], dtype=np.float32)
        
        if len(wbt_data) < 8760: raise ValueError("Incomplete data")
        nan_mask = np.isnan(wbt_data)
        wbt_data[nan_mask] = np.nanmean(wbt_data)
        return wbt_data[:8760]
    except Exception as e:
        print(f"Weather API Failed. Falling back to synthetic. {e}")
        return generate_synthetic_wbt(design_wbt)

def generate_synthetic_wbt(design_wbt: float) -> np.ndarray:
    hours = np.arange(8760)
    hour_of_day = hours % 24
    return design_wbt - 4.0 + 4.0 * np.sin(np.pi * (hour_of_day - 9) / 12)

def get_fluid_cp_density(temp_c: float, is_brine: bool, use_coolprop: bool):
    temp_k = temp_c + 273.15
    if use_coolprop and COOLPROP_AVAILABLE:
        try:
            fluid = 'INCOMP::MEG-30%' if is_brine else 'Water'
            cp = CP.PropsSI('C', 'T', temp_k, 'P', 101325, fluid) / 1000.0 # kJ/kgK
            rho = CP.PropsSI('D', 'T', temp_k, 'P', 101325, fluid) # kg/m3
            return cp, rho
        except: return (3.65, 1045.0) if is_brine else (4.18, 1000.0)
    else:
        return (3.65, 1045.0) if is_brine else (4.18, 1000.0)

def calc_vfd_power(base_kw_tr: float, load_tr: float, rated_tr: float, min_speed: float = 0.35) -> float:
    if rated_tr <= 0 or load_tr <= 0: return 0.0
    flow_ratio = max(min_speed, min(1.0, load_tr / rated_tr))
    return (rated_tr * base_kw_tr) * (flow_ratio ** 3)

def expand_24_to_8760(day1_profile: list) -> np.ndarray:
    return np.tile(np.array(day1_profile, dtype=np.float32), 365)