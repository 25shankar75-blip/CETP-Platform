# optimizer.py
import numpy as np
from typing import Dict, Any
from physics_engine import get_plv_kw_tr, calc_hydraulic_pump_kw
from financial_engine import calculate_capex

def run_8760_simulation(load_profile_8760: np.ndarray, 
                        tariff_profile_8760: np.ndarray, 
                        config: Any, 
                        unit_rates: Dict[str, float]) -> Dict[str, Any]:
    """
    Executes 8,760-hour annual simulation engine comparing:
    1. Conventional N+1 Chiller Plant
    2. PCM TES (8-hr continuous off-peak charging window, sub-zero brine chiller, dynamic arbitrage)
    3. Stratified Chilled Water TES (sensible storage, peak load deficit shaving)
    """
    hours = 8760
    base_chiller_cop = config.thermo.base_chiller_cop
    base_kw_tr = 3.517 / base_chiller_cop if base_chiller_cop > 0 else 0.586
    
    thermo_dict = config.thermo.dict() if hasattr(config.thermo, 'dict') else config.thermo.__dict__
    hydraulic_dict = config.hydraulic.dict() if hasattr(config.hydraulic, 'dict') else config.hydraulic.__dict__
    
    chw_head = hydraulic_dict.get('chw_pump_head_m', 35.0)
    cdw_head = hydraulic_dict.get('cdw_pump_head_m', 25.0)
    brine_head = hydraulic_dict.get('brine_pump_head_m', 45.0)
    pump_eff = hydraulic_dict.get('pump_efficiency', 0.75)
    
    peak_cooling_tr = float(np.max(load_profile_8760))
    daily_avg_cooling_trh = float(np.sum(load_profile_8760[:24]))
    
    results = {}
    
    # ----------------------------------------------------
    # OPTION 1: CONVENTIONAL N+1 CHILLER PLANT
    # ----------------------------------------------------
    conv_installed_tr = peak_cooling_tr * 1.25  # N+1 Redundancy
    
    conv_comp_kw = np.zeros(hours, dtype=np.float32)
    conv_chw_pump_kw = np.zeros(hours, dtype=np.float32)
    conv_cdw_pump_kw = np.zeros(hours, dtype=np.float32)
    conv_ct_fan_kw = np.zeros(hours, dtype=np.float32)
    conv_total_kw = np.zeros(hours, dtype=np.float32)
    
    conv_energy_opex = 0.0
    
    for h in range(hours):
        load_tr = load_profile_8760[h]
        if load_tr > 0:
            hr_of_day = h % 24
            is_night = (hr_of_day < 6 or hr_of_day >= 22)
            load_ratio = load_tr / conv_installed_tr
            
            kw_tr_val = get_plv_kw_tr(load_ratio, base_kw_tr, is_night, thermo_dict)
            comp_pwr = load_tr * kw_tr_val
            
            chw_flow = load_tr * 0.545
            chw_pwr = calc_hydraulic_pump_kw(chw_flow, chw_head, pump_eff, load_ratio)
            
            if "Water" in config.thermo.chiller_type:
                cdw_flow = load_tr * 0.681
                cdw_pwr = calc_hydraulic_pump_kw(cdw_flow, cdw_head, pump_eff, load_ratio)
                ct_pwr = load_tr * 0.035 * max(0.3, load_ratio)
            else:
                cdw_pwr = 0.0
                ct_pwr = 0.0
                
            conv_comp_kw[h] = comp_pwr
            conv_chw_pump_kw[h] = chw_pwr
            conv_cdw_pump_kw[h] = cdw_pwr
            conv_ct_fan_kw[h] = ct_pwr
            
            tot_pwr = comp_pwr + chw_pwr + cdw_pwr + ct_pwr
            conv_total_kw[h] = tot_pwr
            conv_energy_opex += tot_pwr * tariff_profile_8760[h]
            
    conv_peak_kw = float(np.max(conv_total_kw))
    conv_capex = calculate_capex(
        config.project.scope, conv_installed_tr, 0.0, 0.0, "None", 
        unit_rates, conv_peak_kw, config.thermo.chiller_type, config.project.tank_shape
    )
    
    demand_rate_kva = config.financial.demand_charge_per_kva_month
    conv_substation_kva = conv_capex['Substation_kVA']
    conv_annual_demand_opex = conv_substation_kva * demand_rate_kva * 12.0
    conv_total_annual_opex = conv_energy_opex + conv_annual_demand_opex
    
    results["Conventional N+1"] = {
        "Base_Chiller_TR": conv_installed_tr,
        "Brine_Chiller_TR": 0.0,
        "TES_Capacity_TRh": 0.0,
        "Peak_Plant_kW": conv_peak_kw,
        "Substation_kVA": conv_substation_kva,
        "Annual_kWh": float(np.sum(conv_total_kw)),
        "CAPEX": conv_capex,
        "Annual_Energy_OPEX": conv_energy_opex,
        "Annual_Demand_OPEX": conv_annual_demand_opex,
        "Total_Annual_OPEX": conv_total_annual_opex,
        "Simple_Payback_Yrs": 0.0,
        "Comp_kW": conv_comp_kw,
        "CHW_Pump_kW": conv_chw_pump_kw,
        "CDW_Pump_kW": conv_cdw_pump_kw,
        "CT_Fan_kW": conv_ct_fan_kw,
        "Total_kW": conv_total_kw
    }
    
    # ----------------------------------------------------
    # OPTION 2: PCM THERMAL ENERGY STORAGE
    # ----------------------------------------------------
    pcm_shift_trh = daily_avg_cooling_trh * 0.40
    pcm_fom = hydraulic_dict.get('pcm_fom', 0.95)
    pcm_tes_trh = pcm_shift_trh / pcm_fom
    
    pcm_base_chiller_tr = peak_cooling_tr * 0.70
    pcm_brine_chiller_tr = (pcm_tes_trh / 8.0) * 1.10
    
    pcm_comp_kw = np.zeros(hours, dtype=np.float32)
    pcm_chw_pump_kw = np.zeros(hours, dtype=np.float32)
    pcm_cdw_pump_kw = np.zeros(hours, dtype=np.float32)
    pcm_ct_fan_kw = np.zeros(hours, dtype=np.float32)
    pcm_total_kw = np.zeros(hours, dtype=np.float32)
    
    pcm_energy_opex = 0.0
    pcm_derate = thermo_dict.get('pcm_derate_factor', 0.85)
    brine_kw_tr = base_kw_tr / pcm_derate
    
    for h in range(hours):
        hr_of_day = h % 24
        load_tr = load_profile_8760[h]
        tariff = tariff_profile_8760[h]
        
        is_charging = (hr_of_day < 6 or hr_of_day >= 22)
        
        if is_charging:
            base_load_ratio = min(1.0, load_tr / pcm_base_chiller_tr) if pcm_base_chiller_tr > 0 else 0
            base_comp_pwr = load_tr * get_plv_kw_tr(base_load_ratio, base_kw_tr, True, thermo_dict)
            brine_comp_pwr = pcm_brine_chiller_tr * brine_kw_tr
            comp_pwr = base_comp_pwr + brine_comp_pwr
            
            chw_pwr = calc_hydraulic_pump_kw(load_tr * 0.545, chw_head, pump_eff, base_load_ratio)
            brine_pwr = calc_hydraulic_pump_kw(pcm_brine_chiller_tr * 0.60, brine_head, pump_eff, 1.0)
            cdw_pwr = calc_hydraulic_pump_kw((load_tr + pcm_brine_chiller_tr) * 0.681, cdw_head, pump_eff, 0.90) if "Water" in config.thermo.chiller_type else 0.0
            ct_pwr = (load_tr + pcm_brine_chiller_tr) * 0.035 if "Water" in config.thermo.chiller_type else 0.0
        else:
            discharge_rate_tr = min(load_tr, pcm_tes_trh / 16.0)
            rem_chiller_load = max(0.0, load_tr - discharge_rate_tr)
            
            base_load_ratio = rem_chiller_load / pcm_base_chiller_tr if pcm_base_chiller_tr > 0 else 0
            comp_pwr = rem_chiller_load * get_plv_kw_tr(base_load_ratio, base_kw_tr, False, thermo_dict)
            
            chw_pwr = calc_hydraulic_pump_kw(load_tr * 0.545, chw_head, pump_eff, max(0.3, base_load_ratio))
            brine_pwr = calc_hydraulic_pump_kw(discharge_rate_tr * 0.50, 10.0, pump_eff, 1.0)
            cdw_pwr = calc_hydraulic_pump_kw(rem_chiller_load * 0.681, cdw_head, pump_eff, base_load_ratio) if "Water" in config.thermo.chiller_type else 0.0
            ct_pwr = rem_chiller_load * 0.035 * max(0.2, base_load_ratio) if "Water" in config.thermo.chiller_type else 0.0
            
        pcm_comp_kw[h] = comp_pwr
        pcm_chw_pump_kw[h] = chw_pwr
        pcm_cdw_pump_kw[h] = cdw_pwr + brine_pwr
        pcm_ct_fan_kw[h] = ct_pwr
        
        tot_pwr = comp_pwr + chw_pwr + cdw_pwr + brine_pwr + ct_pwr
        pcm_total_kw[h] = tot_pwr
        pcm_energy_opex += tot_pwr * tariff
        
    pcm_peak_kw = float(np.max(pcm_total_kw))
    pcm_capex = calculate_capex(
        config.project.scope, pcm_base_chiller_tr, pcm_brine_chiller_tr, 
        pcm_tes_trh, "PCM", unit_rates, pcm_peak_kw, 
        config.thermo.chiller_type, config.project.tank_shape
    )
    
    pcm_substation_kva = pcm_capex['Substation_kVA']
    pcm_annual_demand_opex = pcm_substation_kva * demand_rate_kva * 12.0
    pcm_total_annual_opex = pcm_energy_opex + pcm_annual_demand_opex
    
    pcm_opex_savings = conv_total_annual_opex - pcm_total_annual_opex
    pcm_inc_capex = pcm_capex['Total_CAPEX'] - conv_capex['Total_CAPEX']
    pcm_payback = (pcm_inc_capex / pcm_opex_savings) if pcm_opex_savings > 0 else 0.0
    
    results["PCM TES System"] = {
        "Base_Chiller_TR": pcm_base_chiller_tr,
        "Brine_Chiller_TR": pcm_brine_chiller_tr,
        "TES_Capacity_TRh": pcm_tes_trh,
        "Peak_Plant_kW": pcm_peak_kw,
        "Substation_kVA": pcm_substation_kva,
        "Annual_kWh": float(np.sum(pcm_total_kw)),
        "CAPEX": pcm_capex,
        "Annual_Energy_OPEX": pcm_energy_opex,
        "Annual_Demand_OPEX": pcm_annual_demand_opex,
        "Total_Annual_OPEX": pcm_total_annual_opex,
        "Annual_OPEX_Savings": pcm_opex_savings,
        "Simple_Payback_Yrs": max(0.0, float(pcm_payback)),
        "Comp_kW": pcm_comp_kw,
        "CHW_Pump_kW": pcm_chw_pump_kw,
        "CDW_Pump_kW": pcm_cdw_pump_kw,
        "CT_Fan_kW": pcm_ct_fan_kw,
        "Total_kW": pcm_total_kw
    }
    
    # ----------------------------------------------------
    # OPTION 3: STRATIFIED CHILLED WATER TES
    # ----------------------------------------------------
    strat_fom = hydraulic_dict.get('strat_fom', 0.90)
    strat_tes_trh = pcm_shift_trh / strat_fom
    strat_base_chiller_tr = peak_cooling_tr * 0.75
    
    strat_comp_kw = np.zeros(hours, dtype=np.float32)
    strat_chw_pump_kw = np.zeros(hours, dtype=np.float32)
    strat_cdw_pump_kw = np.zeros(hours, dtype=np.float32)
    strat_ct_fan_kw = np.zeros(hours, dtype=np.float32)
    strat_total_kw = np.zeros(hours, dtype=np.float32)
    
    strat_energy_opex = 0.0
    
    for h in range(hours):
        hr_of_day = h % 24
        load_tr = load_profile_8760[h]
        tariff = tariff_profile_8760[h]
        
        is_charging = (hr_of_day < 6 or hr_of_day >= 22)
        
        if is_charging:
            charge_tr = (strat_tes_trh / 8.0)
            tot_chiller_load = min(strat_base_chiller_tr * 1.1, load_tr + charge_tr)
            base_load_ratio = tot_chiller_load / strat_base_chiller_tr if strat_base_chiller_tr > 0 else 0
            
            comp_pwr = tot_chiller_load * get_plv_kw_tr(base_load_ratio, base_kw_tr, True, thermo_dict)
            chw_pwr = calc_hydraulic_pump_kw(tot_chiller_load * 0.545, chw_head, pump_eff, base_load_ratio)
            cdw_pwr = calc_hydraulic_pump_kw(tot_chiller_load * 0.681, cdw_head, pump_eff, base_load_ratio) if "Water" in config.thermo.chiller_type else 0.0
            ct_pwr = tot_chiller_load * 0.035 if "Water" in config.thermo.chiller_type else 0.0
        else:
            discharge_rate_tr = min(load_tr, strat_tes_trh / 16.0)
            rem_chiller_load = max(0.0, load_tr - discharge_rate_tr)
            base_load_ratio = rem_chiller_load / strat_base_chiller_tr if strat_base_chiller_tr > 0 else 0
            
            comp_pwr = rem_chiller_load * get_plv_kw_tr(base_load_ratio, base_kw_tr, False, thermo_dict)
            chw_pwr = calc_hydraulic_pump_kw(load_tr * 0.545, chw_head, pump_eff, max(0.3, base_load_ratio))
            cdw_pwr = calc_hydraulic_pump_kw(rem_chiller_load * 0.681, cdw_head, pump_eff, base_load_ratio) if "Water" in config.thermo.chiller_type else 0.0
            ct_pwr = rem_chiller_load * 0.035 * max(0.2, base_load_ratio) if "Water" in config.thermo.chiller_type else 0.0
            
        strat_comp_kw[h] = comp_pwr
        strat_chw_pump_kw[h] = chw_pwr
        strat_cdw_pump_kw[h] = cdw_pwr
        strat_ct_fan_kw[h] = ct_pwr
        
        tot_pwr = comp_pwr + chw_pwr + cdw_pwr + ct_pwr
        strat_total_kw[h] = tot_pwr
        strat_energy_opex += tot_pwr * tariff
        
    strat_peak_kw = float(np.max(strat_total_kw))
    strat_capex = calculate_capex(
        config.project.scope, strat_base_chiller_tr, 0.0, 
        strat_tes_trh, "Stratified", unit_rates, strat_peak_kw, 
        config.thermo.chiller_type, config.project.tank_shape
    )
    
    strat_substation_kva = strat_capex['Substation_kVA']
    strat_annual_demand_opex = strat_substation_kva * demand_rate_kva * 12.0
    strat_total_annual_opex = strat_energy_opex + strat_annual_demand_opex
    
    strat_opex_savings = conv_total_annual_opex - strat_total_annual_opex
    strat_inc_capex = strat_capex['Total_CAPEX'] - conv_capex['Total_CAPEX']
    strat_payback = (strat_inc_capex / strat_opex_savings) if strat_opex_savings > 0 else 0.0
    
    results["Stratified CHW TES"] = {
        "Base_Chiller_TR": strat_base_chiller_tr,
        "Brine_Chiller_TR": 0.0,
        "TES_Capacity_TRh": strat_tes_trh,
        "Peak_Plant_kW": strat_peak_kw,
        "Substation_kVA": strat_substation_kva,
        "Annual_kWh": float(np.sum(strat_total_kw)),
        "CAPEX": strat_capex,
        "Annual_Energy_OPEX": strat_energy_opex,
        "Annual_Demand_OPEX": strat_annual_demand_opex,
        "Total_Annual_OPEX": strat_total_annual_opex,
        "Annual_OPEX_Savings": strat_opex_savings,
        "Simple_Payback_Yrs": max(0.0, float(strat_payback)),
        "Comp_kW": strat_comp_kw,
        "CHW_Pump_kW": strat_chw_pump_kw,
        "CDW_Pump_kW": strat_cdw_pump_kw,
        "CT_Fan_kW": strat_ct_fan_kw,
        "Total_kW": strat_total_kw
    }
    
    return results