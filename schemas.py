# schemas.py
from pydantic import BaseModel, Field
from typing import Literal, Dict

CURRENCY_MULTIPLIERS = {
    "INR (₹)": {"rate": 1.0, "symbol": "₹", "scale_name": "Crores / Lakhs"},
    "USD ($)": {"rate": 1.0 / 83.5, "symbol": "$", "scale_name": "Millions / Thousands"},
    "EUR (€)": {"rate": 1.0 / 90.0, "symbol": "€", "scale_name": "Millions / Thousands"},
    "AED (د.إ)": {"rate": 1.0 / 22.7, "symbol": "د.إ", "scale_name": "Millions / Thousands"},
    "MYR (RM)": {"rate": 1.0 / 18.0, "symbol": "RM", "scale_name": "Millions / Thousands"}
}

class ProjectConfig(BaseModel):
    proj_name: str = Field(default="Example Pharma Project")
    location: str = Field(default="Ujjain, MP, India")
    industry: Literal["Pharmaceuticals", "Data Centre", "Commercial HVAC", "Chemical Process", "FMCG", "Auto"] = Field(default="Pharmaceuticals")
    proj_type: Literal["Greenfield Project", "Brownfield / Retrofit"] = Field(default="Greenfield Project")
    peak_load_tr: float = Field(default=2794.18, gt=0)
    operating_days: int = Field(default=365)
    operating_hours: int = Field(default=24)
    currency: str = Field(default="INR (₹)")
    tes_type: Literal["PCM TES", "STRAT TES"] = Field(default="PCM TES")
    tank_type: Literal["Cylindrical", "Rectangular"] = Field(default="Cylindrical")
    tes_strategy: Literal["Partial Storage", "Full Storage", "Demand Limiting"] = Field(default="Partial Storage")

class ThermoConfig(BaseModel):
    chw_supply: float = Field(default=7.0)
    chw_return: float = Field(default=12.0)
    brine_supply: float = Field(default=-5.0)
    brine_return: float = Field(default=-1.7)
    chiller_type: Literal["Water-Cooled", "Air-Cooled"] = Field(default="Water-Cooled")
    kw_tr_base: float = Field(default=0.58)
    kw_tr_brine: float = Field(default=0.85)

class AuxiliaryConfig(BaseModel):
    chw_pump_kw_tr: float = Field(default=0.078)
    cw_pump_kw_tr: float = Field(default=0.030)
    ct_fan_kw_tr: float = Field(default=0.020)
    brine_pump_kw_tr: float = Field(default=0.020)
    water_evap_l_trh: float = Field(default=1.8)
    grid_emission_factor: float = Field(default=0.716)

class FinancialConfig(BaseModel):
    demand_rate: float = Field(default=475.0)
    water_cost_kl: float = Field(default=25.0)
    indirects_pct: float = Field(default=0.30)
    unit_rates: Dict[str, float] = Field(default_factory=lambda: {
        'water_cooled_chiller': 19000.0, 'air_cooled_chiller': 21000.0, 'brine_chiller': 23000.0,
        'cooling_tower': 3200.0, 'chw_pump': 900.0, 'cdw_pump': 650.0, 'brine_pump': 900.0,
        'phe': 1500.0, 'pcm_cylindrical': 7800.0, 'pcm_rectangular': 8500.0,
        'strat_tes': 18000.0, 'dg_set': 11000.0, 'transformer': 1700.0
    })