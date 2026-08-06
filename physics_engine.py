import math

def get_fluid_properties(fluid_type="Water", temp_c=5.0):
    if fluid_type == "Water":
        return {"cp_kj_kg_k": 4.186, "density_kg_m3": 999.0}
    elif fluid_type == "30% MEG":
        return {"cp_kj_kg_k": 3.65, "density_kg_m3": 1045.0}
    return {"cp_kj_kg_k": 4.186, "density_kg_m3": 1000.0}

def fetch_weather_data(location):
    base_wbt = 24.0
    return [base_wbt + 4.0 * math.sin(2 * math.pi * h / 24) for h in range(8760)]

def calculate_pump_kw(m_dot_kg_s, head_m, efficiency=0.75):
    return (9.81 * m_dot_kg_s * head_m) / (efficiency * 1000)

def get_chiller_plv(part_load_ratio):
    if part_load_ratio >= 1.0: return 1.0
    elif part_load_ratio >= 0.75: return 0.85
    elif part_load_ratio >= 0.50: return 0.70
    else: return 0.60 

def get_dispatch_schedule(hourly_load, tariff_profile, dg_outage_hours, installed_chiller_tr, tes_type="PCM"):
    schedule = []
    
    # Identify the absolute 8 lowest tariff hours for PCM charging
    sorted_tariff_hours = sorted(range(24), key=lambda i: tariff_profile[i])
    pcm_charge_window = sorted_tariff_hours[:8]
    
    # Identify Peak Tariff & DG Outage hours for discharging (highest cost first)
    discharge_priority_hours = sorted(range(24), key=lambda i: (dg_outage_hours[i], tariff_profile[i]), reverse=True)

    for hour in range(24):
        load = hourly_load[hour]
        tariff = tariff_profile[hour]
        
        if tes_type == "PCM":
            # PCM: Dedicated charge chiller runs independently during 8 lowest hours
            is_charging = hour in pcm_charge_window
            is_discharging = hour in discharge_priority_hours[:8] 
            
        elif tes_type == "Stratified":
            # Stratified: Can ONLY charge if existing chillers have spare capacity
            spare_capacity = installed_chiller_tr - load
            is_charging = (tariff <= sorted_tariff_hours[12]) and (spare_capacity > 0)
            is_discharging = hour in discharge_priority_hours[:8]
        else:
            is_charging, is_discharging = False, False
            
        schedule.append({"charge": is_charging, "discharge": is_discharging})
        
    return schedule