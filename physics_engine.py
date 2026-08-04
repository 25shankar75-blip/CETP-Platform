# physics_engine.py
import numpy as np
import requests
from typing import Dict, Any

# ASHRAE Fluid Properties
CP_WATER: float = 4.186  # kJ/kg·K
DENSITY_WATER: float = 1000.0  # kg/m³

CP_BRINE_30MEG: float = 3.65  # kJ/kg·K for 30% Mono Ethylene Glycol
DENSITY_BRINE_30MEG: float = 1045.0  # kg/m³

def get_plv_kw_tr(load_ratio: float, base_kw_tr: float, is_night: bool, thermo_dict: Dict[str, Any]) -> float:
    """
    ASHRAE-compliant Part-Load Value (PLV) efficiency degradation curve
    with night condenser wet-bulb relief bonus multiplier (0.92).
    """
    if load_ratio <= 0.02:
        return 0.0
    
    if load_ratio > 1.0:
        load_ratio = 1.0
        
    plv_factor = 1.15 - 0.45 * load_ratio + 0.30 * (load_ratio ** 2)
    kw_tr = base_kw_tr * plv_factor
    
    if is_night:
        night_relief = thermo_dict.get('night_relief_multiplier', 0.92)
        kw_tr *= night_relief
        
    return max(0.40, float(kw_tr))

def calc_hydraulic_pump_kw(flow_m3_hr: float, head_m: float, efficiency: float, vfd_ratio: float = 1.0) -> float:
    """
    Calculates hydraulic pump power with VFD Affinity Laws:
    kW = (9.81 * mass_flow_kg_s * Head_m) / (Efficiency * 1000) * (VFD_ratio)^3
    """
    if flow_m3_hr <= 0 or efficiency <= 0:
        return 0.0
        
    mass_flow_kg_s = (flow_m3_hr * DENSITY_WATER) / 3600.0
    design_kw = (9.81 * mass_flow_kg_s * head_m) / (efficiency * 1000.0)
    
    vfd_ratio_clamped = max(0.20, min(1.0, vfd_ratio))
    return float(design_kw * (vfd_ratio_clamped ** 3))

def fetch_open_meteo_wbt(lat: float = 23.1793, lon: float = 75.7849) -> np.ndarray:
    """
    Fetches real 8,760-hour Wet Bulb Temperature data via Open-Meteo API.
    Provides synthetic diurnal fallback if connection times out.
    """
    try:
        url = f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date=2023-01-01&end_date=2023-12-31&hourly=wet_bulb_temperature_2m"
        resp = requests.get(url, timeout=4)
        if resp.status_code == 200:
            data = resp.json()
            wbt_array = np.array(data['hourly']['wet_bulb_temperature_2m'], dtype=np.float32)[:8760]
            if len(wbt_array) == 8760:
                return wbt_array
    except Exception:
        pass
        
    hours = np.arange(8760, dtype=np.float32)
    diurnal = 24.0 + 4.0 * np.sin(2 * np.pi * (hours - 9.0) / 24.0)
    seasonal = 3.0 * np.sin(2 * np.pi * (hours - 2000.0) / 8760.0)
    return (diurnal + seasonal).astype(np.float32)

def expand_24_to_8760(day1_profile: list) -> np.ndarray:
    """
    Expands 24-hour profile array across 365 days strictly locking Day 1 (Hours 1-24).
    """
    day1_arr = np.array(day1_profile, dtype=np.float32)
    return np.tile(day1_arr, 365)