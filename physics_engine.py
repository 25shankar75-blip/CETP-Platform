# (CoolProp fluid logic, Affinity Laws, and Open-Meteo API code remains untouched above)

def get_dispatch_schedule(hourly_load, tariff_profile, dg_outage_hours, installed_chiller_tr, tes_type="PCM"):
    """
    Generates a strict 24-hour dispatch schedule mathematically locking 
    PCM to dedicated charging and Stratified to spare-capacity charging.
    """
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
            is_discharging = hour in discharge_priority_hours[:8] # Target top 8 highest cost hours
            
        elif tes_type == "Stratified":
            # Stratified: Can ONLY charge if existing chillers have spare capacity
            spare_capacity = installed_chiller_tr - load
            is_charging = (tariff <= sorted_tariff_hours[12]) and (spare_capacity > 0)
            is_discharging = hour in discharge_priority_hours[:8]
            
        schedule.append({"charge": is_charging, "discharge": is_discharging})
        
    return schedule