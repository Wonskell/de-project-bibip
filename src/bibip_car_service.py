from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from file_table import FileTable
from models import Car, CarFullInfo, CarStatus, Model, ModelSaleStats, Sale


class CarService:
    """A single-writer file database. Open a new instance after restarting."""

    def __init__(self, root_directory_path: str) -> None:
        self.root_directory_path = root_directory_path
        Path(root_directory_path).mkdir(parents=True, exist_ok=True)
        self.cars = FileTable(root_directory_path, "cars", Car, "vin")
        self.models = FileTable(root_directory_path, "models", Model, "id")
        self.sales = FileTable(root_directory_path, "sales", Sale, "sales_number")

    def _require_car(self, vin):
        car = self.cars.get(vin)
        if car is None:
            raise ValueError(f"Unknown car: {vin}")
        return car

    def add_model(self, model: Model) -> Model:
        return self.models.add(model)

    def add_car(self, car: Car) -> Car:
        if self.models.get(car.model) is None:
            raise ValueError(f"Unknown model: {car.model}")
        if car.status == CarStatus.sold:
            raise ValueError("Add a car first, then register its sale")
        return self.cars.add(car)

    def sell_car(self, sale: Sale) -> Car:
        car = self._require_car(sale.car_vin)
        if car.status not in (CarStatus.available, CarStatus.reserve):
            raise ValueError("Only available or reserved cars can be sold")
        if sale.sales_number in self.sales.index:
            raise ValueError(f"Duplicate sale: {sale.sales_number}")
        updated = car.model_copy(update={"status": CarStatus.sold})
        # Validate both record sizes before changing either file.
        self.sales.encode(sale)
        self.cars.encode(updated)
        self.sales.add(sale)
        return self.cars.replace(car.vin, updated)

    def get_cars(self, status: CarStatus) -> list[Car]:
        # Only the requested result is retained, never the entire data file.
        return sorted(
            (car for car in self.cars.scan() if car.status == status),
            key=lambda car: car.vin,
        )

    def get_car_info(self, vin: str) -> CarFullInfo | None:
        car = self.cars.get(vin)
        if car is None:
            return None
        model = self.models.get(car.model)
        if model is None:
            raise ValueError("Car refers to a missing model")
        sale = None
        if car.status == CarStatus.sold:
            sale = next((s for s in self.sales.scan() if s.car_vin == vin), None)
            if sale is None:
                raise ValueError("Sold car has no sale record")
        return CarFullInfo(
            vin=car.vin, car_model_name=model.name, car_model_brand=model.brand,
            price=car.price, date_start=car.date_start, status=car.status,
            sales_date=sale.sales_date if sale else None,
            sales_cost=sale.cost if sale else None,
        )

    def update_vin(self, vin: str, new_vin: str) -> Car:
        car = self._require_car(vin)
        if not new_vin:
            raise ValueError("VIN cannot be empty")
        if new_vin != vin and new_vin in self.cars.index:
            raise ValueError(f"Duplicate VIN: {new_vin}")
        updated = car.model_copy(update={"vin": new_vin})
        self.cars.encode(updated)
        # Preserve references even when correcting a sold car.
        for sale in self.sales.scan():
            if sale.car_vin == vin:
                self.sales.encode(sale.model_copy(update={"car_vin": new_vin}))
        self.cars.replace(vin, updated)
        for sale in self.sales.scan():
            if sale.car_vin == vin:
                self.sales.replace(
                    sale.sales_number, sale.model_copy(update={"car_vin": new_vin})
                )
        return updated

    def revert_sale(self, sales_number: str) -> Car:
        sale = self.sales.get(sales_number)
        if sale is None:
            raise ValueError(f"Unknown sale: {sales_number}")
        car = self._require_car(sale.car_vin)
        updated = car.model_copy(update={"status": CarStatus.available})
        self.cars.encode(updated)
        self.sales.delete(sales_number)
        return self.cars.replace(car.vin, updated)

    def top_models_by_sales(self) -> list[ModelSaleStats]:
        # Aggregate by model only; no list of sales or cars is materialized.
        counts = defaultdict(int)
        totals = defaultdict(Decimal)
        for sale in self.sales.scan():
            car = self._require_car(sale.car_vin)
            counts[car.model] += 1
            totals[car.model] += sale.cost
        # "More expensive" is defined as mean sale price; id breaks exact ties.
        ranked = sorted(
            counts, key=lambda mid: (-counts[mid], -totals[mid] / counts[mid], mid)
        )[:3]
        result = []
        for mid in ranked:
            model = self.models.get(mid)
            result.append(ModelSaleStats(
                car_model_name=model.name, brand=model.brand,
                sales_number=counts[mid],
            ))
        return result
