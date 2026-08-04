# financial_engine.py
from typing import Dict, Any

def size_electrical_infrastructure(peak_kw: float, rates: Dict[str, float]) -> Dict[str, float]:
    """
    Sizes Transformer and Emergency Diesel Generator (DG Set) kVA capacity:
    kVA = (Peak kW / 0.80 Power Factor) * 1.25 Safety Margin
    """
    if peak_kw <= 0:
        return {"substation_kva": 0.0, "transformer_capex": 0.0, "dg_capex": 0.0, "total_elec_capex": 0.0}
        
    req_kva = (peak_kw / 0.80) * 1.25
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
                    peak_kw: float, chiller_type: str = "Water-Cooled Centrifugal",
                    tank_shape: str = "Cylindrical") -> Dict[str, Any]:
    """
    Calculates full equipment CAPEX enforcing strict Greenfield vs. Brownfield (sunk-cost) logic.
    """
    is_brownfield = (scope == "Brownfield (Retrofit)") or (scope == "Brownfield")
    
    chiller_rate = rates.get('water_cooled_chiller', 17000.0) if "Water" in chiller_type else rates.get('air_cooled_chiller', 19000.0)
    
    # Greenfield: Full equipment CAPEX.
    # Brownfield: Existing base chillers are SUNK COST (₹0 CAPEX).
    base_chiller_capex = 0.0 if is_brownfield else (base_chiller_tr * chiller_rate)
    
    # Sub-zero brine chiller for PCM charging is ALWAYS new CAPEX
    brine_chiller_capex = (brine_chiller_tr * rates.get('brine_chiller', 23000.0)) if (tes_type == "PCM" and brine_chiller_tr > 0) else 0.0
    
    # TES Storage Tank CAPEX
    if tes_type == "PCM":
        pcm_rate = rates.get('pcm_tes_rectangular', 8475.0) if "Rectangular" in tank_shape else rates.get('pcm_tes_cylindrical', 7533.0)
        tes_tank_capex = tes_trh * pcm_rate
    elif tes_type == "Stratified":
        tes_tank_capex = tes_trh * rates.get('strat_tes', 18000.0)
    else:
        tes_tank_capex = 0.0
        
    # Ancillary Systems
    ct_capex = 0.0 if is_brownfield else (base_chiller_tr * rates.get('cooling_tower', 2200.0))
    chw_pump_capex = base_chiller_tr * rates.get('chw_pump', 700.0)
    cdw_pump_capex = (base_chiller_tr * rates.get('cdw_pump', 550.0)) if "Water" in chiller_type else 0.0
    brine_pump_capex = (brine_chiller_tr * rates.get('brine_pump', 900.0)) if tes_type == "PCM" else 0.0
    phe_capex = (base_chiller_tr * rates.get('phe', 1100.0)) if tes_type in ["PCM", "Stratified"] else 0.0
    
    ancillary_total = ct_capex + chw_pump_capex + cdw_pump_capex + brine_pump_capex + phe_capex
    
    # Electrical Infrastructure (Substation + DG Set)
    elec_infra = size_electrical_infrastructure(peak_kw, rates)
    
    total_capex = base_chiller_capex + brine_chiller_capex + tes_tank_capex + ancillary_total + elec_infra['total_elec_capex']
    
    return {
        "Base_Chillers": base_chiller_capex,
        "Brine_Chillers": brine_chiller_capex,
        "TES_Tank": tes_tank_capex,
        "Ancillary_CT_Pumps_PHE": ancillary_total,
        "Electrical_Substation_DG": elec_infra['total_elec_capex'],
        "Substation_kVA": elec_infra['substation_kva'],
        "Total_CAPEX": total_capex
    }

def format_currency(val: float, currency_str: str) -> str:
    """Formats numbers into Lakhs/Crores for INR and standard commas for foreign currencies."""
    if "INR" in currency_str or "₹" in currency_str:
        if abs(val) >= 10_000_000:
            return f"₹ {val / 10_000_000:.2f} Cr"
        elif abs(val) >= 100_000:
            return f"₹ {val / 100_000:.2f} Lakhs"
        else:
            return f"₹ {val:,.2f}"
    else:
        symbol = "$" if "$" in currency_str else ("€" if "€" in currency_str else ("AED " if "AED" in currency_str else "RM "))
        return f"{symbol}{val:,.2f}"