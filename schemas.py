from pydantic import BaseModel, Field
from typing import Literal, Dict, List

CURRENCY_MULTIPLIERS = {
    "INR (₹)": {"rate": 1.0, "symbol": "₹", "scale_name": "Crores / Lakhs"},
    "USD ($)": {"rate": 1.0 / 83.5, "symbol": "$", "scale_name": "Millions / Thousands"},
    "EUR (€)": {"rate": 1.0 / 90.0, "symbol": "€", "scale_name": "Millions / Thousands"},
    "AED (د.إ)": {"rate": 1.0 / 22.7, "symbol": "د.إ", "scale_name": "Millions / Thousands"},
    "MYR (RM)": {"rate": 1.0 / 18.0, "symbol": "RM", "scale_name": "Millions / Thousands"}
}

class ProjectConfig(BaseModel):
    proj_name: str = Field(default="Mondelez Industrial Retrofit")
    location: str = Field(default="Pune, Maharashtra, India")
    industry: Literal["Pharmaceuticals", "Data Centre", "Commercial HVAC", "Chemical Process", "FMCG", "Auto"] = Field(default="FMCG")
    proj_type: Literal["Greenfield Project", "Brownfield / Retrofit"] = Field(default="Brownfield / Retrofit")
    currency: str = Field(default="INR (₹)")
    tes_strategy: Literal["Partial Storage", "Full Storage", "Demand Limiting"] = Field(default="Partial Storage")
    tank_shape: Literal["Cylindrical", "Rectangular"] = Field(default="Cylindrical")
    use_live_weather: bool = Field(default=True)
    use_coolprop: bool = Field(default=True)

class ThermoConfig(BaseModel):
    chiller_type: Literal["Water-Cooled", "Air-Cooled"] = Field(default="Water-Cooled")
    design_wbt: float = Field(default=28.0)
    chw_supply: float = Field(default=7.0)
    chw_return: float = Field(default=12.0)
    brine_supply: float = Field(default=-5.5)
    brine_return: float = Field(default=-2.1)
    kw_tr_base: float = Field(default=0.60)
    kw_tr_brine: float = Field(default=0.85)

class AuditConfig(BaseModel):
    ext_kw_tr_base: float = Field(default=0.85)
    ext_chw_flow: float = Field(default=477.0)
    ext_chw_sup: float = Field(default=5.2)
    ext_chw_ret: float = Field(default=7.6)
    ext_chw_head: float = Field(default=40.0)
    ext_cw_flow: float = Field(default=739.0)
    ext_cw_sup: float = Field(default=32.0)
    ext_cw_ret: float = Field(default=35.0)
    ext_cw_head: float = Field(default=35.0)
    ext_ct_fan_kw: float = Field(default=21.0)

class FinancialConfig(BaseModel):
    operating_days: int = Field(default=325)
    dg_outage_hrs: float = Field(default=2.5)
    dg_tariff: float = Field(default=28.0)
    demand_rate: float = Field(default=475.0)
    water_cost_kl: float = Field(default=25.0)
    grid_emission: float = Field(default=0.727)
    evap_loss: float = Field(default=1.8)
    indirects_pct: float = Field(default=0.30)
    maintenance_pct: float = Field(default=0.015) 
    unit_rates: Dict[str, float] = Field(default_factory=lambda: {
        'water_cooled_chiller': 19000.0, 'air_cooled_chiller': 21000.0, 'brine_chiller': 23000.0,
        'cooling_tower': 3200.0, 'chw_pump': 900.0, 'cdw_pump': 650.0, 'brine_pump': 900.0,
        'phe': 1500.0, 'pcm_cylindrical': 7800.0, 'pcm_rectangular': 8500.0,
        'strat_tes': 18000.0, 'dg_set': 11000.0, 'transformer': 1700.0
    })