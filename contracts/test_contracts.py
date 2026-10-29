"""Contract validation tests for OpenAPI specs and JSON fixtures."""

import json
from pathlib import Path
import pytest
import yaml
from jsonschema import validate, Draft202012Validator

CONTRACTS_DIR = Path(__file__).resolve().parent
OPENAPI_DIR = CONTRACTS_DIR / "openapi"
FIXTURES_DIR = CONTRACTS_DIR / "fixtures"


@pytest.fixture(scope="session")
def components():
    """Load canonical components schema definitions."""
    comp_file = OPENAPI_DIR / "components.yaml"
    assert comp_file.exists(), f"components.yaml not found at {comp_file}"
    with open(comp_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data["components"]["schemas"]


def test_openapi_files_exist_and_valid():
    """Verify that all required OpenAPI 3.1 YAML specifications exist and parse cleanly."""
    required_services = [
        "core-api",
        "ingest-ai",
        "genai",
        "forecast",
        "optimizer",
        "coldchain",
        "sim-control",
        "sim-hospital",
    ]
    for svc in required_services:
        yaml_path = OPENAPI_DIR / f"{svc}.yaml"
        assert yaml_path.exists(), f"Missing OpenAPI spec for {svc}: {yaml_path}"
        with open(yaml_path, "r", encoding="utf-8") as f:
            spec = yaml.safe_load(f)
        assert spec.get("openapi") in ("3.1.0", "3.0.3", "3.0.0")
        assert "info" in spec
        assert "paths" in spec
        assert len(spec["paths"]) > 0


def _validate_with_components(data, schema, all_components):
    """Validate data against a schema with resolved local component refs."""
    schema_copy = json.loads(json.dumps(schema))
    # Wrap in root with components so local #/components/schemas references resolve
    root = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "components": {"schemas": all_components},
        **schema_copy,
    }
    validator = Draft202012Validator(root)
    validator.validate(data)


def test_facilities_fixture(components):
    with open(FIXTURES_DIR / "facilities.json", "r", encoding="utf-8") as f:
        facilities = json.load(f)
    assert len(facilities) >= 4
    array_schema = {"type": "array", "items": components["Facility"]}
    _validate_with_components(facilities, array_schema, components)


def test_drugs_fixture(components):
    with open(FIXTURES_DIR / "drugs.json", "r", encoding="utf-8") as f:
        drugs = json.load(f)
    assert len(drugs) >= 3
    array_schema = {"type": "array", "items": components["Drug"]}
    _validate_with_components(drugs, array_schema, components)


def test_routes_fixture(components):
    with open(FIXTURES_DIR / "routes.json", "r", encoding="utf-8") as f:
        routes = json.load(f)
    array_schema = {"type": "array", "items": components["Route"]}
    _validate_with_components(routes, array_schema, components)


def test_vehicles_fixture(components):
    with open(FIXTURES_DIR / "vehicles.json", "r", encoding="utf-8") as f:
        vehicles = json.load(f)
    array_schema = {"type": "array", "items": components["Vehicle"]}
    _validate_with_components(vehicles, array_schema, components)


def test_lots_fixture(components):
    with open(FIXTURES_DIR / "lots.json", "r", encoding="utf-8") as f:
        lots = json.load(f)
    array_schema = {"type": "array", "items": components["Lot"]}
    _validate_with_components(lots, array_schema, components)


def test_positions_fixture(components):
    with open(FIXTURES_DIR / "positions.json", "r", encoding="utf-8") as f:
        positions = json.load(f)
    array_schema = {"type": "array", "items": components["Position"]}
    _validate_with_components(positions, array_schema, components)


def test_plan_fixture_and_orders(components):
    """Verify plan.json satisfies PlanRun schema and has exactly 6 orders, with 1 insulin usable=28 from 50 lot."""
    with open(FIXTURES_DIR / "plan.json", "r", encoding="utf-8") as f:
        plan = json.load(f)

    # Validate PlanRun schema
    _validate_with_components(plan, components["PlanRun"], components)

    # Check 6 orders constraint
    orders = plan.get("orders", [])
    assert len(orders) == 6, f"Expected 6 orders in plan fixture, found {len(orders)}"

    # Check insulin order constraint
    insulin_orders = [o for o in orders if o.get("drug_code") == "INS-REG"]
    assert len(insulin_orders) >= 1, "Expected at least one insulin order in plan"
    ins_order = insulin_orders[0]
    assert ins_order.get("lot_quantity") == 50, "Expected lot quantity of 50 for insulin"
    assert ins_order.get("usable_quantity") == 28, "Expected usable quantity of 28 for insulin"
    assert ins_order.get("quantity") == 28, "Expected transfer quantity of 28 for insulin"


def test_orders_fixture(components):
    with open(FIXTURES_DIR / "orders.json", "r", encoding="utf-8") as f:
        orders = json.load(f)
    assert len(orders) == 6
    array_schema = {"type": "array", "items": components["TransferOrder"]}
    _validate_with_components(orders, array_schema, components)


def test_order_single_fixture(components):
    with open(FIXTURES_DIR / "order_single.json", "r", encoding="utf-8") as f:
        order = json.load(f)
    _validate_with_components(order, components["TransferOrder"], components)


def test_custody_events_fixture(components):
    with open(FIXTURES_DIR / "custody_events.json", "r", encoding="utf-8") as f:
        events = json.load(f)
    array_schema = {"type": "array", "items": components["CustodyEvent"]}
    _validate_with_components(events, array_schema, components)


def test_audit_verify_fixture(components):
    with open(FIXTURES_DIR / "audit_verify.json", "r", encoding="utf-8") as f:
        audit = json.load(f)
    _validate_with_components(audit, components["AuditVerify"], components)


def test_reports_fixture(components):
    with open(FIXTURES_DIR / "reports.json", "r", encoding="utf-8") as f:
        reports = json.load(f)
    array_schema = {"type": "array", "items": components["StockReport"]}
    _validate_with_components(reports, array_schema, components)


def test_llm_complete_fixture(components):
    with open(FIXTURES_DIR / "llm_complete.json", "r", encoding="utf-8") as f:
        resp = json.load(f)
    _validate_with_components(resp, components["LlmResponse"], components)


def test_forecast_fixture(components):
    with open(FIXTURES_DIR / "forecast.json", "r", encoding="utf-8") as f:
        forecasts = json.load(f)
    array_schema = {"type": "array", "items": components["Forecast"]}
    _validate_with_components(forecasts, array_schema, components)
