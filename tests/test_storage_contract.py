from datetime import datetime
from decimal import Decimal
import json

import pytest
from bibip_car_service import CarService
from models import Car, CarStatus, Model, Sale


def car(vin, model=1, price="100", status=CarStatus.available):
    return Car(vin=vin, model=model, price=Decimal(price),
               date_start=datetime(2024, 1, 1), status=status)


def sale(number, vin, cost="200"):
    return Sale(sales_number=number, car_vin=vin, cost=Decimal(cost),
                sales_date=datetime(2024, 2, 1))


@pytest.fixture
def service(tmp_path):
    s = CarService(str(tmp_path))
    s.add_model(Model(id=1, name="Модель ё", brand="Марка"))
    return s


def test_persistence_unicode_and_sorted_vins(service, tmp_path):
    service.add_car(car("Z"))
    service.add_car(car("A", price="123.45"))
    reopened = CarService(str(tmp_path))
    assert [c.vin for c in reopened.get_cars(CarStatus.available)] == ["A", "Z"]
    assert reopened.get_car_info("A").car_model_name == "Модель ё"
    assert reopened.get_car_info("A").price == Decimal("123.45")
    for name in ("cars", "models", "sales"):
        assert (tmp_path / f"{name}.txt").exists()
        assert (tmp_path / f"{name}_index.txt").exists()
        assert (tmp_path / f"{name}.txt").stat().st_size % 501 == 0


def test_duplicate_keys_and_missing_references(service):
    service.add_car(car("A"))
    with pytest.raises(ValueError):
        service.add_car(car("A"))
    with pytest.raises(ValueError):
        service.add_model(Model(id=1, name="Other", brand="Other"))
    with pytest.raises(ValueError):
        service.add_car(car("B", model=999))
    with pytest.raises(ValueError):
        service.sell_car(sale("S1", "missing"))
    assert service.get_car_info("missing") is None
    assert len(service.get_cars(CarStatus.available)) == 1


def test_sale_duplicate_and_revert_middle_record(service, tmp_path):
    for vin in ("C", "A", "B"):
        service.add_car(car(vin))
        service.sell_car(sale("S" + vin, vin))
    with pytest.raises(ValueError):
        service.sell_car(sale("SC", "A"))
    with pytest.raises(ValueError):
        service.sell_car(sale("OTHER", "A"))
    assert service.revert_sale("SA").status == CarStatus.available
    reopened = CarService(str(tmp_path))
    assert reopened.get_car_info("B").sales_cost == Decimal("200")
    assert reopened.get_car_info("A").sales_date is None
    assert reopened.top_models_by_sales()[0].sales_number == 2
    with pytest.raises(ValueError):
        reopened.revert_sale("SA")
    reopened.sell_car(sale("SA2", "A"))
    assert reopened.top_models_by_sales()[0].sales_number == 3


def test_vin_change_updates_index_and_sale(service, tmp_path):
    service.add_car(car("Z"))
    service.add_car(car("B"))
    service.sell_car(sale("S1", "Z"))
    with pytest.raises(ValueError):
        service.update_vin("Z", "B")
    service.update_vin("Z", "A")
    reopened = CarService(str(tmp_path))
    assert reopened.get_car_info("Z") is None
    assert reopened.get_car_info("A").sales_cost == Decimal("200")
    assert reopened.revert_sale("S1").vin == "A"
    assert [c.vin for c in reopened.get_cars(CarStatus.available)] == ["A", "B"]
    rows = [json.loads(x) for x in (tmp_path / "cars_index.txt").read_text().splitlines()]
    assert [x[0] for x in rows] == ["A", "B"]


def test_top_tie_uses_mean_sale_price_and_excludes_unsold(service):
    for mid in (2, 3, 4):
        service.add_model(Model(id=mid, name=str(mid), brand="B"))
    for vin, mid, cost in (("a", 1, "100"), ("b", 2, "500"), ("c", 3, "300")):
        service.add_car(car(vin, model=mid))
        service.sell_car(sale(vin, vin, cost))
    service.add_car(car("unsold", model=4, price="99999"))
    assert [x.car_model_name for x in service.top_models_by_sales()] == ["2", "3", "Модель ё"]


def test_oversize_record_does_not_change_files(service, tmp_path):
    before = (tmp_path / "models.txt").read_bytes()
    with pytest.raises(ValueError):
        service.add_model(Model(id=2, name="Я" * 600, brand="B"))
    assert (tmp_path / "models.txt").read_bytes() == before


def test_empty_database(tmp_path):
    s = CarService(str(tmp_path))
    assert s.get_cars(CarStatus.available) == []
    assert s.top_models_by_sales() == []
    assert s.get_car_info("missing") is None
