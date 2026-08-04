# optimizer.py
import numpy as np
from typing import Dict, Any
from physics_engine import get_plv_kw_tr, calc_hydraulic_pump_kw
from financial_engine import calculate_capex

def run_8760_simulation(load_8760: np.ndarray, tariff_8760: np.ndarray, config: Any, rates: Dict[str, float]) -> Dict[str, Any]:
    hours = 8760
    peak_tr = float(np.max(load_8760))
    daily_trh = float(np.sum(load_8760[:24]))
    base_kw_tr = 3.517 / config.thermo.base_chiller_cop
    
    results = {}
    
    # --- 1. CONVENTIONAL N+1 ---
    # Mandatory +25% Redundancy pushes Conventional CAPEX and Substation kVA extremely high
    conv_tr = peak_tr * 1.25 
    conv_kw = np.zeros(hours, dtype=np.float32)
    conv_opex = 0.0
    
    for h in range(hours):
        load = load_8760[h]
        if load > 0:
            is_night = (h % 24 < 6 or h % 24 >= 22)
            vfd_ratio = load / conv_tr
            comp = load * get_plv_kw_tr(vfd_ratio, base_kw_tr, is_night, config.thermo.__dict__)
            pump = calc_hydraulic_pump_kw(load*0.545, config.hydraulic.chw_pump_head_m, config.hydraulic.pump_efficiency, vfd_ratio)
            cdw = calc_hydraulic_pump_kw(load*0.681, config.hydraulic.cdw_pump_head_m, config.hydraulic.pump_efficiency, vfd_ratio) if "Water" in config.thermo.chiller_type else 0
            fan = load * 0.035 * max(0.3, vfd_ratio) if "Water" in config.thermo.chiller_type else 0
            tot = comp + pump + cdw + fan
            conv_kw[h] = tot
            conv_opex += tot * tariff_8760[h]
            
    conv_peak_kw = float(np.max(conv_kw))
    conv_cap = calculate_capex(config.project.scope, conv_tr, 0, 0, "None", rates, conv_peak_kw, config.thermo.chiller_type, config.project.tank_shape)
    conv_dem = conv_cap['Substation_kVA'] * config.financial.demand_charge_per_kva_month * 12
    
    results["Conventional N+1"] = {
        "Base_TR": conv_tr, "Brine_TR": 0, "TES_TRh": 0, "Peak_kW": conv_peak_kw, "Sub_kVA": conv_cap['Substation_kVA'],
        "CAPEX": conv_cap, "En_OPEX": conv_opex, "Dem_OPEX": conv_dem, "Tot_OPEX": conv_opex + conv_dem,
        "Total_kW": conv_kw, "Charge_TRh": 0, "Discharge_TRh": 0
    }
    
    # --- 2. PCM TES (8hr Window Aggressive Downsizing) ---
    charge_hrs = 8.0
    # Aggressively downsize base chiller by 35%
    pcm_base_tr = peak_tr * 0.65 
    pcm_shift_trh = daily_trh * 0.35
    pcm_tes_trh = pcm_shift_trh / config.hydraulic.pcm_fom
    pcm_brine_tr = (pcm_tes_trh / charge_hrs) * 1.05
    
    pcm_kw = np.zeros(hours, dtype=np.float32)
    pcm_opex = 0.0
    brine_kw_tr = base_kw_tr / config.thermo.pcm_derate_factor
    
    for h in range(hours):
        load = load_8760[h]
        hr_of_day = h % 24
        is_charging = (hr_of_day < 6 or hr_of_day >= 22)
        
        if is_charging:
            vfd_ratio = min(1.0, load / pcm_base_tr)
            comp = (load * get_plv_kw_tr(vfd_ratio, base_kw_tr, True, config.thermo.__dict__)) + (pcm_brine_tr * brine_kw_tr)
            pump = calc_hydraulic_pump_kw(load*0.545, config.hydraulic.chw_pump_head_m, 0.75, vfd_ratio) + calc_hydraulic_pump_kw(pcm_brine_tr*0.6, config.hydraulic.brine_pump_head_m, 0.75, 1.0)
            cdw = calc_hydraulic_pump_kw((load+pcm_brine_tr)*0.681, config.hydraulic.cdw_pump_head_m, 0.75, 0.9) if "Water" in config.thermo.chiller_type else 0
            fan = (load+pcm_brine_tr)*0.035 if "Water" in config.thermo.chiller_type else 0
        else:
            discharge_tr = min(load, pcm_tes_trh / 16.0)
            rem_load = max(0.0, load - discharge_tr)
            vfd_ratio = rem_load / pcm_base_tr if pcm_base_tr > 0 else 0
            comp = rem_load * get_plv_kw_tr(vfd_ratio, base_kw_tr, False, config.thermo.__dict__)
            pump = calc_hydraulic_pump_kw(load*0.545, config.hydraulic.chw_pump_head_m, 0.75, max(0.3, vfd_ratio)) + calc_hydraulic_pump_kw(discharge_tr*0.5, 10.0, 0.75, 1.0)
            cdw = calc_hydraulic_pump_kw(rem_load*0.681, config.hydraulic.cdw_pump_head_m, 0.75, vfd_ratio) if "Water" in config.thermo.chiller_type else 0
            fan = rem_load*0.035*max(0.2, vfd_ratio) if "Water" in config.thermo.chiller_type else 0
            
        tot = comp + pump + cdw + fan
        pcm_kw[h] = tot
        pcm_opex += tot * tariff_8760[h]
        
    pcm_peak_kw = float(np.max(pcm_kw)) # Will be much lower than conventional
    pcm_cap = calculate_capex(config.project.scope, pcm_base_tr, pcm_brine_tr, pcm_tes_trh, "PCM", rates, pcm_peak_kw, config.thermo.chiller_type, config.project.tank_shape)
    pcm_dem = pcm_cap['Substation_kVA'] * config.financial.demand_charge_per_kva_month * 12
    
    results["PCM TES"] = {
        "Base_TR": pcm_base_tr, "Brine_TR": pcm_brine_tr, "TES_TRh": pcm_tes_trh, "Peak_kW": pcm_peak_kw, "Sub_kVA": pcm_cap['Substation_kVA'],
        "CAPEX": pcm_cap, "En_OPEX": pcm_opex, "Dem_OPEX": pcm_dem, "Tot_OPEX": pcm_opex + pcm_dem,
        "Total_kW": pcm_kw, "Charge_TRh": pcm_brine_tr * charge_hrs, "Discharge_TRh": pcm_shift_trh
    }

    # --- 3. STRATIFIED CHW TES ---
    strat_base_tr = peak_tr * 0.70 # Downsized 30%
    strat_shift_trh = daily_trh * 0.30
    strat_tes_trh = strat_shift_trh / config.hydraulic.strat_fom
    strat_kw = np.zeros(hours, dtype=np.float32)
    strat_opex = 0.0
    
    for h in range(hours):
        load = load_8760[h]
        hr_of_day = h % 24
        is_charging = (hr_of_day < 6 or hr_of_day >= 22)
        
        if is_charging:
            tot_load = min(strat_base_tr*1.05, load + (strat_tes_trh/8.0))
            vfd_ratio = tot_load / strat_base_tr
            comp = tot_load * get_plv_kw_tr(vfd_ratio, base_kw_tr, True, config.thermo.__dict__)
            pump = calc_hydraulic_pump_kw(tot_load*0.545, config.hydraulic.chw_pump_head_m, 0.75, vfd_ratio)
            cdw = calc_hydraulic_pump_kw(tot_load*0.681, config.hydraulic.cdw_pump_head_m, 0.75, vfd_ratio) if "Water" in config.thermo.chiller_type else 0
            fan = tot_load*0.035 if "Water" in config.thermo.chiller_type else 0
        else:
            discharge_tr = min(load, strat_tes_trh / 16.0)
            rem_load = max(0.0, load - discharge_tr)
            vfd_ratio = rem_load / strat_base_tr if strat_base_tr > 0 else 0
            comp = rem_load * get_plv_kw_tr(vfd_ratio, base_kw_tr, False, config.thermo.__dict__)
            pump = calc_hydraulic_pump_kw(load*0.545, config.hydraulic.chw_pump_head_m, 0.75, max(0.3, vfd_ratio))
            cdw = calc_hydraulic_pump_kw(rem_load*0.681, config.hydraulic.cdw_pump_head_m, 0.75, vfd_ratio) if "Water" in config.thermo.chiller_type else 0
            fan = rem_load*0.035*max(0.2, vfd_ratio) if "Water" in config.thermo.chiller_type else 0
            
        tot = comp + pump + cdw + fan
        strat_kw[h] = tot
        strat_opex += tot * tariff_8760[h]
        
    strat_peak_kw = float(np.max(strat_kw))
    strat_cap = calculate_capex(config.project.scope, strat_base_tr, 0, strat_tes_trh, "Stratified", rates, strat_peak_kw, config.thermo.chiller_type, config.project.tank_shape)
    strat_dem = strat_cap['Substation_kVA'] * config.financial.demand_charge_per_kva_month * 12
    
    results["Stratified TES"] = {
        "Base_TR": strat_base_tr, "Brine_TR": 0, "TES_TRh": strat_tes_trh, "Peak_kW": strat_peak_kw, "Sub_kVA": strat_cap['Substation_kVA'],
        "CAPEX": strat_cap, "En_OPEX": strat_opex, "Dem_OPEX": strat_dem, "Tot_OPEX": strat_opex + strat_dem,
        "Total_kW": strat_kw, "Charge_TRh": strat_tes_trh * config.hydraulic.strat_fom, "Discharge_TRh": strat_shift_trh
    }

    # Add Payback logic comparing against Conventional
    conv_cap_tot = results["Conventional N+1"]["CAPEX"]["Total_CAPEX"]
    conv_op_tot = results["Conventional N+1"]["Tot_OPEX"]
    
    for sys in ["PCM TES", "Stratified TES"]:
        inc_cap = results[sys]["CAPEX"]["Total_CAPEX"] - conv_cap_tot
        op_save = conv_op_tot - results[sys]["Tot_OPEX"]
        results[sys]["Savings"] = op_save
        results[sys]["Payback"] = (inc_cap / op_save) if op_save > 0 and inc_cap > 0 else (0.0 if inc_cap <= 0 else 99.9)

    return results