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
    proj_name: str = Field(default="Pharma Greenfield Plant")
    location: str = Field(default="Ujjain, MP, India")
    industry: Literal["Pharmaceuticals", "Data Centre", "Commercial HVAC", "Chemical Process", "FMCG", "Auto"] = Field(default="Pharmaceuticals")
    proj_type: Literal["Greenfield Project", "Brownfield / Retrofit"] = Field(default="Greenfield Project")
    peak_load_tr: float = Field(default=2794.18, gt=0)
    tank_shape: Literal["Cylindrical (API 650)", "Rectangular Concrete/Steel"] = Field(default="Cylindrical (API 650)")
    currency: Literal["INR (₹)", "USD ($)", "EUR (€)", "AED (د.إ)", "MYR (RM)"] = Field(default="INR (₹)")

class ThermoConfig(BaseModel):
    chw_supply: float = Field(default=7.0)
    chw_return: float = Field(default=12.0)
    brine_supply: float = Field(default=-5.5)
    brine_return: float = Field(default=-1.7)
    chiller_type: Literal["Water-Cooled (With Cooling Towers)", "Air-Cooled"] = Field(default="Water-Cooled (With Cooling Towers)")

class HydraulicConfig(BaseModel):
    head_chw: float = Field(default=40.0)
    head_cw: float = Field(default=30.0)
    head_phe_penalty: float = Field(default=10.0)
    pump_efficiency: float = Field(default=0.70)
    ct_fan_ikw_tr: float = Field(default=0.015)
    pcm_fom: float = Field(default=0.95)
    strat_fom: float = Field(default=0.90)

class FinancialConfig(BaseModel):
    demand_rate: float = Field(default=475.0)
    unit_rates: Dict[str, float] = Field(default_factory=lambda: {
        'water_cooled_chiller': 17000.0, 'air_cooled_chiller': 19000.0, 'brine_chiller': 23000.0,
        'cooling_tower': 2200.0, 'chw_pump': 700.0, 'cdw_pump': 550.0, 'brine_pump': 900.0,
        'phe': 1100.0, 'pcm_tes_cylindrical': 7533.0, 'pcm_tes_rectangular': 8475.0,
        'strat_tes': 18000.0, 'dg_set': 11000.0, 'transformer': 1700.0
    })
    kw_tr_base: float = Field(default=0.58)
    kw_tr_brine: float = Field(default=0.85)