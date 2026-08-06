"""
CETP Digital Twin - Data Schemas & Configurations
File: schemas.py
"""
from pydantic import BaseModel, Field
from enum import Enum

CURRENCY_MULTIPLIERS = {
    "INR (₹)": {"rate": 1.0, "symbol": "₹", "unit": "Cr", "div": 1e7},
    "USD ($)": {"rate": 0.012, "symbol": "$", "unit": "M", "div": 1e6},
    "EUR (€)": {"rate": 0.011, "symbol": "€", "unit": "M", "div": 1e6},
    "AED (د.إ)": {"rate": 0.044, "symbol": "AED", "unit": "M", "div": 1e6},
    "MYR (RM)": {"rate": 0.053, "symbol": "RM", "unit": "M", "div": 1e6}
}

class ScopeEnum(str, Enum):
    GREENFIELD = "Greenfield"
    BROWNFIELD = "Brownfield (Retrofit)"

class ThermoConfig(BaseModel):
    chw_supply_c: float = 7.0
    chw_return_c: float = 14.0
    brine_supply_c: float = -5.5
    phe_pinch_c: float = 1.5
    fom_efficiency: float = 0.90
    water_cp: float = 4.186       # kJ/kg.K
    brine_cp: float = 3.65        # 30% MEG
    water_rho: float = 1000.0     # kg/m3
    brine_rho: float = 1035.0

class FinancialConfig(BaseModel):
    base_chiller_rate: float = 22000.0
    brine_chiller_rate: float = 25000.0
    pcm_tes_rate: float = 7800.0
    stratified_tes_rate: float = 18000.0
    dg_set_rate: float = 12500.0
    indirects_pct: float = 0.30