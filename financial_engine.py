# financial_engine.py
def calculate_capex(scope: str, chiller_tr: float, tes_trh: float, tes_type: str, rates: dict) -> dict:
    """Calculates CAPEX enforcing Brownfield zero-sunk-cost on base chillers."""
    is_brownfield = (scope == "Brownfield")
    
    # Base chiller cost is ZERO in brownfield (already exists)
    chiller_capex = 0 if is_brownfield else (chiller_tr * rates['base_chiller'])
    
    # Sub-zero brine chillers are always new capex
    brine_chiller_capex = 0
    if tes_type == "PCM":
        brine_chiller_capex = chiller_tr * rates['brine_chiller'] # Dedicated charging
        tes_capex = tes_trh * rates['pcm_tes']
    elif tes_type == "Stratified":
        tes_capex = tes_trh * rates['strat_tes']
    else:
        tes_capex = 0

    cooling_tower = 0 if is_brownfield else (chiller_tr * rates['cooling_tower'])
    pumps_capex = (chiller_tr * (rates['chw_pump'] + rates['cdw_pump']))
    
    total = chiller_capex + brine_chiller_capex + cooling_tower + pumps_capex + tes_capex
    
    return {
        "Chillers": chiller_capex + brine_chiller_capex,
        "TES System": tes_capex,
        "Ancillary (Pumps/CT)": cooling_tower + pumps_capex,
        "Total": total
    }

def size_electrical_infrastructure(peak_kw: float, rates: dict) -> dict:
    """Sizes DG Set and Transformer based on peak load."""
    dg_kva = (peak_kw / 0.8) * 1.25 # 80% pf, 25% safety margin
    return {
        "DG_kVA": dg_kva,
        "DG_Capex": dg_kva * rates['dg_set'],
        "Transformer_Capex": dg_kva * rates['transformer']
    }