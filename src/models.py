from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import AliasChoices, BaseModel, Field


class CarStatus(StrEnum):
    available = "available"
    reserve = "reserve"
    sold = "sold"
    delivery = "delivery"


class Car(BaseModel):
    vin: str
    model: int
    price: Decimal
    date_start: datetime
    status: CarStatus

    def index(self) -> str:
        return self.vin


class Model(BaseModel):
    id: int
    name: str
    brand: str

    def index(self) -> str:
        return str(self.id)


class Sale(BaseModel):
    sales_number: str
    car_vin: str
    sales_date: datetime
    cost: Decimal

    def index(self) -> str:
        return self.sales_number


class CarFullInfo(BaseModel):
    vin: str
    model_name: str = Field(validation_alias=AliasChoices("model_name", "car_model_name"))
    model_brand: str = Field(validation_alias=AliasChoices("model_brand", "car_model_brand"))
    price: Decimal
    date_start: datetime
    status: CarStatus
    sales_date: datetime | None
    sales_cost: Decimal | None

    # Compatibility with the names used in the original course template.
    @property
    def car_model_name(self) -> str:
        return self.model_name

    @property
    def car_model_brand(self) -> str:
        return self.model_brand


class ModelSaleStats(BaseModel):
    car_model_name: str
    brand: str
    sales_count: int = Field(validation_alias=AliasChoices("sales_count", "sales_number"))

    @property
    def sales_number(self) -> int:
        return self.sales_count
