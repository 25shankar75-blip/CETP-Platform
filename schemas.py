"""
Cooling Energy Transition Platform (CETP) - Data Contracts & Schemas
File: schemas.py
"""
from pydantic import BaseModel
from typing import Optional
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

class TankShapeEnum(str, Enum):
    CYLINDRICAL = "Cylindrical Tank"
    RECTANGULAR = "Rectangular Tank"

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
    AC_SCROLL = "Air-Cooled Scroll"
    BRINE_GLYCOL = "Sub-Zero Brine Chiller"
    DUAL_MODE = "Dual-Mode Chiller"

class ProjectConfig(BaseModel):
    project_name: Optional[str] = None
    location: Optional[str] = None
    sector: str = SectorEnum.FMCG.value
    scope: str = ScopeEnum.GREENFIELD.value
    currency: str = "INR (₹)"
    tank_shape: str = TankShapeEnum.CYLINDRICAL.value
    peak_tr: Optional[float] = None
    running_days: Optional[int] = None
    chiller_module_tr: Optional[float] = None
    project_life_years: Optional[int] = None

class AuditConfig(BaseModel):
    run_chw_sup_c: Optional[float] = None
    run_chw_ret_c: Optional[float] = None
    run_chw_head_m: Optional[float] = None
    run_sec_chw_head_m: Optional[float] = None
    run_cw_sup_c: Optional[float] = None
    run_cw_ret_c: Optional[float] = None
    run_cw_head_m: Optional[float] = None
    run_chw_flow_m3h: Optional[float] = None
    run_sec_chw_flow_m3h: Optional[float] = None
    run_cw_flow_m3h: Optional[float] = None
    run_ct_fan_kw: Optional[float] = None
    water_cost_per_m3: Optional[float] = None
    
    # Rev 19 Chiller Performance Baselines
    kw_tr_base: Optional[float] = None
    kw_tr_brine: Optional[float] = None
    kw_tr_ac: Optional[float] = None

class FinancialConfig(BaseModel):
    base_chiller_rate: Optional[float] = None
    ac_chiller_rate: Optional[float] = None
    brine_chiller_rate: Optional[float] = None
    pcm_cyl_rate: Optional[float] = None
    pcm_rect_rate: Optional[float] = None
    stratified_tes_rate: Optional[float] = None
    dg_set_rate: Optional[float] = None
    transformer_rate: Optional[float] = None
    water_infra_rate: Optional[float] = None
    indirects_pct: Optional[float] = None
    dg_diesel_cost_kwh: Optional[float] = None
    daily_outage_hrs: Optional[float] = None
    
    # Rev 19 Economic Escalators
    discount_rate_pct: Optional[float] = None
    elec_escalation_pct: Optional[float] = None
    water_escalation_pct: Optional[float] = None