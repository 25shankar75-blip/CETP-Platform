# physics_engine.py
import numpy as np
import requests

# Specific Heats (kJ/kg.K)
CP_WATER = 4.18
CP_BRINE_30MEG = 3.65
DENSITY_WATER = 1000 # kg/m3
DENSITY_BRINE = 1045 # kg/m3

def get_plv_kw_tr(load_ratio: float, base_efficiency: float, is_night: bool, thermo: dict) -> float:
    """ASHRAE Part-Load Value (PLV) degradation curve with Night Condenser Relief."""
    if load_ratio <= 0.05:
        return 0.0
    # Standard quadratic degradation curve
    plv = base_efficiency * (1.15 - 0.15 * load_ratio + 0.05 * (load_ratio ** 2))
    if is_night:
        plv *= thermo['night_relief_multiplier']
    return max(0.5, plv) # Hard floor on efficiency

def calc_hydraulic_pump_kw(flow_m3_hr: float, head_m: float, efficiency: float, vfd_ratio: float = 1.0) -> float:
    """Calculates pump power with VFD Affinity Laws (Power is proportional to cube of flow ratio)."""
    if flow_m3_hr <= 0: return 0.0
    mass_flow_kg_s = (flow_m3_hr * DENSITY_WATER) / 3600
    design_kw = (9.81 * mass_flow_kg_s * head_m) / (efficiency * 1000)
    # VFD Affinity Law
    return design_kw * (vfd_ratio ** 3)

def fetch_open_meteo_wbt(lat: float, lon: float) -> np.ndarray:
    """Fetches real historical 8760hr WBT via Open-Meteo API. Returns synthetic fallback if fails."""
    try:
        url = f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date=2023-01-01&end_date=2023-12-31&hourly=wet_bulb_temperature_2m"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return np.array(data['hourly']['wet_bulb_temperature_2m'], dtype=np.float32)[:8760]
    except Exception:
        pass
    # Fallback: Synthetic sine wave for WBT
    hours = np.arange(8760)
    return np.array(22 + 4 * np.sin(2 * np.pi * (hours - 8) / 24), dtype=np.float32)

def expand_24_to_8760(day1_profile: list) -> np.ndarray:
    """Expands user 24h baseline strictly locking Day 1 without floating errors."""
    return np.tile(np.array(day1_profile, dtype=np.float32), 365)