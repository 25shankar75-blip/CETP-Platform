"""
CETP Digital Twin - Pydantic Data Schemas
File: schemas.py
"""

from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum

class ScopeEnum(str, Enum):
    GREENFIELD = "Greenfield"
    BROWNFIELD = "Brownfield (Retrofit)"

class SectorEnum(str, Enum):
    PHARMA = "Pharmaceutical"
    DATA_CENTRE = "Data Centre"
    FMCG = "FMCG"
    AUTO = "Auto"
    COMMERCIAL = "Commercial"

class CurrencyEnum(str, Enum):
    INR = "INR (₹)"
    USD = "USD ($)"
    EUR = "EUR (€)"
    AED = "AED (د.إ)"
    MYR = "MYR (RM)"

class ChillerTypeEnum(str, Enum):
    WC_CENTRIFUGAL = "Water-Cooled Centrifugal"
    WC_VFD_SCREW = "Water-Cooled VFD Screw"
    AC_VFD = "Air-Cooled VFD"
    BRINE_GLYCOL = "Sub-Zero Brine Chiller"

class ChillerSpec(BaseModel):
    capacity_tr: float = Field(..., gt=0)
    quantity: int = Field(..., gt=0)
    chiller_type: ChillerTypeEnum

class ProjectConfig(BaseModel):
    project_name: str = "Mondelez 3017 TRh Retrofit"
    location: str = "Ujjain, MP"
    sector: SectorEnum = SectorEnum.FMCG
    scope: ScopeEnum = ScopeEnum.BROWNFIELD
    currency: CurrencyEnum = CurrencyEnum.INR
    peak_tr: float = 2794.18

class ThermoConfig(BaseModel):
    chw_supply_temp: float = 7.0
    chw_return_temp: float = 14.0
    brine_supply_temp: float = -5.5
    brine_return_temp: float = -2.1
    phe_pinch_deg_c: float = 1.5
    fom_efficiency: float = 0.90

class AuditConfig(BaseModel):
    running_chw_supply_c: float = 8.0
    running_chw_return_c: float = 12.0
    running_chw_flow_m3h: float = 500.0
    running_cw_supply_c: float = 32.0
    running_cw_return_c: float = 37.0
    running_cw_flow_m3h: float = 600.0
    chw_pump_head_m: float = 30.0
    cw_pump_head_m: float = 25.0
    ct_fan_power_kw: float = 45.0
    actual_kw_per_tr: float = 0.91

class FinancialConfig(BaseModel):
    base_chiller_rate_per_tr: float = 22000.0
    brine_chiller_rate_per_tr: float = 25000.0
    pcm_tes_rate_per_trh: float = 7800.0
    stratified_tes_rate_per_trh: float = 18000.0
    dg_set_rate_per_kva: float = 12500.0
    electricity_tariff_avg: float = 6.11
    dg_diesel_cost_per_kwh: float = 24.50
    daily_outage_hours: float = 1.5
    indirects_pct: float = 0.30