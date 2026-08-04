# financial_engine.py
from typing import Dict, Any

def size_electrical_infrastructure(peak_kw: float, rates: Dict[str, float]) -> Dict[str, float]:
    """Sizes Substation & DG Set based on Max Plant kW (Massive savings for TES)."""
    req_kva = (peak_kw / 0.80) * 1.25 # 80% PF, 25% Safety margin
    transformer_cost = req_kva * rates.get('transformer', 1700.0)
    dg_cost = req_kva * rates.get('dg_set', 11000.0)
    return {
        "substation_kva": float(req_kva),
        "transformer_capex": float(transformer_cost),
        "dg_capex": float(dg_cost),
        "total_elec_capex": float(transformer_cost + dg_cost)
    }

def calculate_capex(scope: str, base_chiller_tr: float, brine_chiller_tr: float, 
                    tes_trh: float, tes_type: str, rates: Dict[str, float], 
                    peak_kw: float, chiller_type: str, tank_shape: str) -> Dict[str, Any]:
    """Applies strict Brownfield zero-sunk-cost logic and highly optimized Greenfield logic."""
    is_brownfield = "Brownfield" in scope
    
    chiller_rate = rates.get('water_cooled_chiller', 17000.0) if "Water" in chiller_type else rates.get('air_cooled_chiller', 19000.0)
    
    base_chiller_capex = 0.0 if is_brownfield else (base_chiller_tr * chiller_rate)
    brine_chiller_capex = (brine_chiller_tr * rates.get('brine_chiller', 23000.0)) if tes_type == "PCM" else 0.0
    
    if tes_type == "PCM":
        pcm_rate = rates.get('pcm_tes_rectangular', 8475.0) if "Rectangular" in tank_shape else rates.get('pcm_tes_cylindrical', 7533.0)
        tes_tank_capex = tes_trh * pcm_rate
    elif tes_type == "Stratified":
        tes_tank_capex = tes_trh * rates.get('strat_tes', 18000.0)
    else:
        tes_tank_capex = 0.0
        
    ct_capex = 0.0 if is_brownfield else (base_chiller_tr * rates.get('cooling_tower', 2200.0))
    pumps_capex = (base_chiller_tr * rates.get('chw_pump', 700.0)) + ((base_chiller_tr * rates.get('cdw_pump', 550.0)) if "Water" in chiller_type else 0)
    brine_pump_capex = (brine_chiller_tr * rates.get('brine_pump', 900.0)) if tes_type == "PCM" else 0.0
    phe_capex = (base_chiller_tr * rates.get('phe', 1100.0)) if tes_type in ["PCM", "Stratified"] else 0.0
    
    ancillary_total = ct_capex + pumps_capex + brine_pump_capex + phe_capex
    elec_infra = size_electrical_infrastructure(peak_kw, rates)
    
    return {
        "Base_Chillers": base_chiller_capex,
        "Brine_Chillers": brine_chiller_capex,
        "TES_Tank": tes_tank_capex,
        "Ancillary_CT_Pumps_PHE": ancillary_total,
        "Electrical_Substation_DG": elec_infra['total_elec_capex'],
        "Substation_kVA": elec_infra['substation_kva'],
        "Total_CAPEX": base_chiller_capex + brine_chiller_capex + tes_tank_capex + ancillary_total + elec_infra['total_elec_capex']
    }

def format_currency(val: float, currency_str: str) -> str:
    if "INR" in currency_str or "₹" in currency_str:
        if abs(val) >= 10_000_000: return f"₹ {val / 10_000_000:.2f} Cr"
        elif abs(val) >= 100_000: return f"₹ {val / 100_000:.2f} Lakhs"
        else: return f"₹ {val:,.0f}"
    else:
        symbol = "$" if "$" in currency_str else ("€" if "€" in currency_str else ("AED " if "AED" in currency_str else "RM "))
        return f"{symbol}{val:,.0f}"