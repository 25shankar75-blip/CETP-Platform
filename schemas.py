from pydantic import BaseModel, Field
from typing import List

class ChillerUnit(BaseModel):
    capacity_tr: float = Field(default=500.0, description="Capacity of a single chiller in TR")
    quantity: int = Field(default=1, description="Number of chillers of this capacity")
    chiller_type: str = Field(default="Water-Cooled Centrifugal", description="Type of Chiller")

class ProjectConfig(BaseModel):
    project_name: str
    location: str
    sector: str
    scope: str = Field(default="Greenfield") # "Greenfield" or "Retrofit"
    chiller_fleet: List[ChillerUnit] = Field(default_factory=lambda: [ChillerUnit()])
    tank_shape: str = Field(default="Cylindrical")
    currency: str = Field(default="INR (₹)")
    
    @property
    def total_installed_tr(self) -> float:
        # Dynamically calculates total plant TR based on fleet array
        return sum([unit.capacity_tr * unit.quantity for unit in self.chiller_fleet])

# (ThermoConfig, AuditConfig, FinancialConfig remain completely unchanged below this)