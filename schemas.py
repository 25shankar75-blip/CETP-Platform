"""
Cooling Energy Transition Platform (CETP) - Data Contracts & Schemas
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

class SectorEnum(str, Enum):
    PHARMA = "Pharmaceutical"
    DATA_CENTRE = "Data Centre"
    FMCG = "FMCG"
    AUTO = "Auto"
    COMMERCIAL = "Commercial"

class ChillerTypeEnum(str, Enum):
    WC_CENTRIFUGAL = "Water-Cooled Centrifugal"
    WC_VFD_SCREW = "Water-Cooled VFD Screw"
    AC_VFD = "Air-Cooled VFD"
    BRINE_GLYCOL = "Sub-Zero Brine Chiller"

class ProjectConfig(BaseModel):
    project_name: str = "Mondelez 3017 TRh Retrofit"
    location: str = "Gurugram, HR"
    sector: SectorEnum = SectorEnum.FMCG
    scope: ScopeEnum = ScopeEnum.BROWNFIELD
    currency: str = "INR (₹)"
    peak_tr: float = 2794.18

class ThermoConfig(BaseModel):
    chw_supply_c: float = 7.0
    chw_return_c: float = 14.0
    brine_supply_c: float = -5.5
    phe_pinch_c: float = 1.5

class AuditConfig(BaseModel):
    # Measured running parameters for Brownfield Thermodynamics
    run_chw_sup_c: float = 8.0
    run_chw_ret_c: float = 12.0
    run_chw_flow_m3h: float = 500.0
    run_chw_head_m: float = 30.0
    run_cw_sup_c: float = 32.0
    run_cw_ret_c: float = 37.0
    run_cw_flow_m3h: float = 600.0
    run_cw_head_m: float = 25.0
    run_ct_fan_kw: float = 45.0
    pump_efficiency: float = 0.75

class FinancialConfig(BaseModel):
    base_chiller_rate: float = 22000.0
    brine_chiller_rate: float = 25000.0
    pcm_tes_rate: float = 7800.0
    stratified_tes_rate: float = 18000.0
    dg_set_rate: float = 12500.0
    indirects_pct: float = 0.30