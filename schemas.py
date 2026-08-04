# schemas.py
from pydantic import BaseModel
from typing import Dict

CURRENCY_MULTIPLIERS = {
    "INR (₹)": 1.0,
    "USD ($)": 0.012,
    "EUR (€)": 0.011,
    "AED (د.إ)": 0.044,
    "MYR (RM)": 0.056
}

class ProjectConfig(BaseModel):
    project_name: str
    location: str
    sector: str
    scope: str # "Greenfield" or "Brownfield"
    currency: str
    peak_load_tr: float
    
class ThermoConfig(BaseModel):
    chiller_type: str # "Water-Cooled" or "Air-Cooled"
    design_wbt: float
    pcm_charge_temp: float = -5.5
    stratified_charge_temp: float = 4.0
    pcm_derate_factor: float = 0.85 # sub-zero COP penalty
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
    electricity_tariff: Dict[str, float] # off_peak, normal, peak
    demand_charge_per_kva: float
    unit_rates: Dict[str, float]