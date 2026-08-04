# physics_engine.py
import numpy as np

PLV_LOADS = np.array([0.0, 0.25, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 1.00])
PLV_MULT = np.array([1.50, 1.32, 1.20, 1.09, 1.02, 0.96, 0.92, 0.94, 1.00])

def get_plv_kw_tr(load_fraction: float, full_load_kw_tr: float) -> float:
    safe_fraction = max(0.0, min(1.0, load_fraction))
    multiplier = np.interp(safe_fraction, PLV_LOADS, PLV_MULT)
    return full_load_kw_tr * multiplier

def get_night_condenser_bonus(hour_of_day: int) -> float:
    if hour_of_day <= 6 or hour_of_day >= 22: return 0.92
    return 1.0

def calc_pump_ikw_tr(delta_t_c: float, head_m: float, efficiency: float, is_brine: bool = False) -> float:
    if delta_t_c <= 0: return 0.0
    cp = 3.65 if is_brine else 4.18
    m_dot = 3.517 / (cp * delta_t_c)
    return (9.81 * m_dot * head_m) / (efficiency * 1000.0)

def calc_vfd_pump_power(base_ikw_tr: float, load_tr: float, rated_tr: float, min_speed_ratio: float = 0.35) -> float:
    if rated_tr <= 0 or load_tr <= 0: return 0.0
    flow_ratio = max(min_speed_ratio, min(1.0, load_tr / rated_tr))
    design_power = rated_tr * base_ikw_tr
    return design_power * (flow_ratio ** 3) 

def expand_24_to_8760(day1_profile: list) -> np.ndarray:
    return np.tile(np.array(day1_profile, dtype=np.float32), 365)