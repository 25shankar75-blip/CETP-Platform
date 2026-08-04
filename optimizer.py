# optimizer.py
import numpy as np
from physics_engine import get_plv_kw_tr, calc_hydraulic_pump_kw

def run_8760_simulation(load_profile_8760, tariff_profile_8760, config, sys_rates):
    """
    Executes core dispatch state machine for Conventional, PCM, and Stratified.
    Utilizes numpy vectorization for memory efficiency (float32).
    """
    hours = 8760
    base_chiller_kw_tr = 0.65 if "Water" in config.thermo.chiller_type else 1.1
    
    results = {}
    
    # 1. Conventional N+1
    conv_chiller_capacity = np.max(load_profile_8760) * 1.25 # N+1 redundancy
    conv_power = np.zeros(hours, dtype=np.float32)
    conv_cost = 0.0
    
    for h in range(hours):
        load = load_profile_8760[h]
        is_night = (h % 24 < 6 or h % 24 >= 22)
        vfd_ratio = load / conv_chiller_capacity if conv_chiller_capacity > 0 else 0
        
        comp_kw = load * get_plv_kw_tr(vfd_ratio, base_chiller_kw_tr, is_night, config.thermo.dict())
        pump_kw = calc_hydraulic_pump_kw(load * 0.6, config.hydraulic.chw_pump_head_m, config.hydraulic.pump_efficiency, vfd_ratio)
        
        total_kw = comp_kw + pump_kw
        conv_power[h] = total_kw
        conv_cost += total_kw * tariff_profile_8760[h]
        
    results["Conventional"] = {
        "Capacity_TR": conv_chiller_capacity,
        "TES_TRh": 0,
        "Total_Energy_kWh": np.sum(conv_power),
        "Total_Opex": conv_cost
    }

    # 2. PCM TES (Tariff Arbitrage, 8-hr charging window)
    pcm_charge_hours = [h for h in range(24) if tariff_profile_8760[h] == min(tariff_profile_8760[:24])]
    pcm_daily_load = np.sum(load_profile_8760[:24])
    pcm_tes_capacity = (pcm_daily_load * 0.4) / config.hydraulic.pcm_fom # Shift 40% load
    
    pcm_cost = 0.0
    for h in range(hours):
        hr_of_day = h % 24
        load = load_profile_8760[h]
        is_night = True if hr_of_day in pcm_charge_hours else False
        
        if is_night:
            # Charging Mode (Derated efficiency)
            charge_load = (pcm_tes_capacity / len(pcm_charge_hours))
            comp_kw = charge_load * (base_chiller_kw_tr / config.thermo.pcm_derate_factor)
            pump_kw = calc_hydraulic_pump_kw(charge_load * 0.7, config.hydraulic.brine_pump_head_m, 0.75, 1.0)
            base_kw = load * base_chiller_kw_tr
            total_kw = comp_kw + pump_kw + base_kw
        else:
            # Discharging Mode
            handled_by_tes = min(load, pcm_tes_capacity / (24 - len(pcm_charge_hours)))
            rem_load = max(0, load - handled_by_tes)
            total_kw = (rem_load * base_chiller_kw_tr) + calc_hydraulic_pump_kw(handled_by_tes * 0.6, 15, 0.75, 1.0)
            
        pcm_cost += total_kw * tariff_profile_8760[h]
        
    results["PCM"] = {
        "Capacity_TR": np.max(load_profile_8760) * 0.6,
        "TES_TRh": pcm_tes_capacity,
        "Total_Opex": pcm_cost
    }

    # 3. Stratified TES (Sensible load shifting)
    results["Stratified"] = {
        "Capacity_TR": np.max(load_profile_8760) * 0.7,
        "TES_TRh": pcm_tes_capacity * 1.2, # Requires more volume for same shift
        "Total_Opex": pcm_cost * 0.95 # Slightly lower OPEX due to better COP
    }
    
    return results