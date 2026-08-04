# physics_engine.py
import numpy as np

CP_WATER: float = 4.186
DENSITY_WATER: float = 1000.0

def get_plv_kw_tr(load_ratio: float, base_kw_tr: float, is_night: bool, thermo_dict: dict) -> float:
    """ASHRAE PLV with Night WBT Relief."""
    if load_ratio <= 0.05: return 0.0
    load_ratio = min(1.0, load_ratio)
    
    plv_factor = 1.15 - 0.45 * load_ratio + 0.30 * (load_ratio ** 2)
    kw_tr = base_kw_tr * plv_factor
    
    if is_night:
        kw_tr *= thermo_dict.get('night_relief_multiplier', 0.92)
        
    return max(0.40, float(kw_tr))

def calc_hydraulic_pump_kw(flow_m3_hr: float, head_m: float, efficiency: float, vfd_ratio: float = 1.0) -> float:
    """VFD Affinity Cube Law (kW drops massively at part load)."""
    if flow_m3_hr <= 0 or efficiency <= 0: return 0.0
    mass_flow_kg_s = (flow_m3_hr * DENSITY_WATER) / 3600.0
    design_kw = (9.81 * mass_flow_kg_s * head_m) / (efficiency * 1000.0)
    
    vfd_ratio_clamped = max(0.25, min(1.0, vfd_ratio)) # Minimum pump speed 25%
    return float(design_kw * (vfd_ratio_clamped ** 3))

def expand_24_to_8760(day1_profile: list) -> np.ndarray:
    return np.tile(np.array(day1_profile, dtype=np.float32), 365)