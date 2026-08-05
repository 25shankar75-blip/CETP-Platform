# physics_engine.py
import numpy as np

# Exact Part-Load Curve from Rev19 Input
PLV_LOADS = np.array([0.0, 0.25, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 1.00])
PLV_KW_TR = np.array([0.75, 0.70, 0.64, 0.58, 0.54, 0.51, 0.49, 0.50, 0.53])

def get_plv_kw_tr(load_fraction: float) -> float:
    safe_fraction = max(0.0, min(1.0, load_fraction))
    return float(np.interp(safe_fraction, PLV_LOADS, PLV_KW_TR))

def get_night_condenser_bonus(hour_of_day: int) -> float:
    # 0.92 multiplier active from 22:00 to 06:00
    if hour_of_day <= 6 or hour_of_day >= 22: return 0.92
    return 1.0

def calc_vfd_power(base_kw_tr: float, load_tr: float, rated_tr: float, min_speed: float = 0.35) -> float:
    if rated_tr <= 0 or load_tr <= 0: return 0.0
    flow_ratio = max(min_speed, min(1.0, load_tr / rated_tr))
    design_power = rated_tr * base_kw_tr
    return design_power * (flow_ratio ** 3)

def expand_24_to_8760(day1_profile: list) -> np.ndarray:
    return np.tile(np.array(day1_profile, dtype=np.float32), 365)