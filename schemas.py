from pydantic import BaseModel, Field
from typing import List

class ChillerUnit(BaseModel):
    capacity_tr: float = Field(default=500.0, description="Capacity of a single chiller in TR")
    quantity: int = Field(default=1, description="Number of chillers of this capacity")
    chiller_type: str = Field(default="Water-Cooled Centrifugal", description="Type of Chiller")

class ProjectConfig(BaseModel):
    project_name: str = "CETP Digital Twin"
    location: str = "Gurugram, India"
    sector: str = "Industrial"
    scope: str = Field(default="Greenfield") # "Greenfield" or "Retrofit (Brownfield)"
    chiller_fleet: List[ChillerUnit] = Field(default_factory=lambda: [ChillerUnit()])
    tank_shape: str = Field(default="Cylindrical")
    currency: str = Field(default="INR (₹)")
    
    @property
    def total_installed_tr(self) -> float:
        return sum([unit.capacity_tr * unit.quantity for unit in self.chiller_fleet])

class ThermoConfig(BaseModel):
    chw_supply_temp_c: float = 5.0
    chw_return_temp_c: float = 14.0
    ambient_wbt_c: float = 28.0
    pcm_brine_temp_c: float = -6.0

class FinancialConfig(BaseModel):
    electricity_tariff_peak: float = 12.0
    electricity_tariff_offpeak: float = 6.0
    dg_generation_cost: float = 22.0
    discount_rate: float = 0.10
    project_life_years: int = 20

class AuditConfig(BaseModel):
    baseline_kw_tr: float = 0.65
    pump_efficiency: float = 0.75
    system_fom: float = 0.90