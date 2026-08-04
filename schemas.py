# schemas.py
from pydantic import BaseModel, Field
from typing import Dict, Any

CURRENCY_MULTIPLIERS: Dict[str, float] = {
    "INR (₹)": 1.0,
    "USD ($)": 0.012,
    "EUR (€)": 0.011,
    "AED (د.إ)": 0.044,
    "MYR (RM)": 0.056
}

CURRENCY_SYMBOLS: Dict[str, str] = {
    "INR (₹)": "₹",
    "USD ($)": "$",
    "EUR (€)": "€",
    "AED (د.إ)": "AED",
    "MYR (RM)": "RM"
}

class ProjectConfig(BaseModel):
    project_name: str = "Ujjain Pharma Greenfield Baseline"
    location: str = "Ujjain, MP, India"
    sector: str = "Pharmaceutical"
    scope: str = "Greenfield" 
    currency: str = "INR (₹)"
    peak_load_tr: float = 2794.18
    tank_shape: str = "Cylindrical"

class ThermoConfig(BaseModel):
    chiller_type: str = "Water-Cooled Centrifugal"
    base_chiller_cop: float = 6.0
    design_wbt: float = 28.0
    pcm_charge_temp: float = -5.5
    pcm_derate_factor: float = 0.85 
    night_relief_multiplier: float = 0.92 

class HydraulicConfig(BaseModel):
    chw_delta_t: float = 6.0
    pcm_fom: float = 0.95
    strat_fom: float = 0.90
    chw_pump_head_m: float = 35.0
    cdw_pump_head_m: float = 25.0
    brine_pump_head_m: float = 45.0
    pump_efficiency: float = 0.75

class FinancialConfig(BaseModel):
    demand_charge_per_kva_month: float = 475.0
    unit_rates: Dict[str, float] = Field(default_factory=lambda: {
        'water_cooled_chiller': 17000.0,
        'air_cooled_chiller': 19000.0,
        'brine_chiller': 23000.0,
        'cooling_tower': 2200.0,
        'chw_pump': 700.0,
        'cdw_pump': 550.0,
        'brine_pump': 900.0,
        'phe': 1100.0,
        'pcm_tes_cylindrical': 7533.0,
        'pcm_tes_rectangular': 8475.0,
        'strat_tes': 18000.0,
        'dg_set': 11000.0,
        'transformer': 1700.0
    })