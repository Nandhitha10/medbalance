"""Unit and integration tests for simulated hospital nodes across all 4 reporting styles."""

from datetime import date, datetime
import pytest
from httpx import ASGITransport, AsyncClient

from medbal_common.clock import KOLKATA_TZ
from sim_hospital import (
    HospitalDB,
    HospitalNode,
    generate_chat_report,
    generate_stock_csv,
    generate_fhir_inventory_report,
    generate_messy_register_note,
)


def test_fefo_dispensing_and_expiry():
    """Verify hospital local SQLite database dispenses FEFO and expires lots at date threshold."""
    db = HospitalDB(db_path=":memory:")
    # Seed 2 lots of insulin: one expiring in 5 days, one in 20 days
    db.load_initial_stock([
        {"drug_code": "INS-REG", "batch_no": "LOT-NEAR", "expiry": "2026-11-05", "quantity": 10},
        {"drug_code": "INS-REG", "batch_no": "LOT-FAR", "expiry": "2026-11-20", "quantity": 25},
    ])

    # Dispense 15 units: 10 should come from LOT-NEAR (exhausting it), 5 from LOT-FAR
    dispensed, stockout = db.dispense_fefo("INS-REG", demand=15, day_index=1, current_date_str="2026-11-01")
    assert dispensed == 15
    assert stockout == 0

    inv = db.get_inventory()
    # LOT-NEAR is exhausted (qty 0 so not returned by get_inventory)
    assert len(inv) == 1
    assert inv[0]["batch_no"] == "LOT-FAR"
    assert inv[0]["quantity"] == 20

    # Advance time to 2026-11-21 -> LOT-FAR expires
    expired_cnt = db.expire_lots("2026-11-21")
    assert expired_cnt == 1
    assert len(db.get_inventory()) == 0


def test_h1_fhir_inventory_report_rendering():
    """Verify H1 FHIR R5/R4 InventoryReport generation."""
    inventory = [
        {"drug_code": "INS-REG", "batch_no": "LOT-INS-H1-01", "expiry": "2026-11-21", "quantity": 2},
        {"drug_code": "OXY-10", "batch_no": "LOT-OXY-H1-01", "expiry": "2026-11-23", "quantity": 3},
    ]
    dt = datetime(2026, 11, 1, 8, 0, tzinfo=KOLKATA_TZ)
    report = generate_fhir_inventory_report("H1", "SIM-DH Jayanagar", inventory, dt)

    assert report["resourceType"] == "InventoryReport"
    assert report["countType"] == "snapshot"
    assert report["status"] == "completed"
    assert len(report["inventoryListing"]) == 2

    ins_listing = report["inventoryListing"][0]
    assert ins_listing["lot"] == "LOT-INS-H1-01"
    assert ins_listing["quantity"]["value"] == 2
    assert ins_listing["quantity"]["unit"] == "vial"


def test_h2_csv_export_unit_conversion_and_irregularity():
    """Verify H2 CSV converts tablets to strips and simulates missing batch numbers."""
    inventory = [
        {"drug_code": "PCM-500", "batch_no": "LOT-PCM-01", "expiry": "2026-11-21", "quantity": 8000},
        {"drug_code": "AMOX-500", "batch_no": "LOT-AMX-02", "expiry": "2026-11-23", "quantity": 3500},
        {"drug_code": "INS-REG", "batch_no": "LOT-INS-03", "expiry": "2026-12-01", "quantity": 50},
    ]
    csv_text = generate_stock_csv(inventory)
    lines = csv_text.strip().split("\n")

    # Header
    assert lines[0] == "Drug Name,Batch No,Exp Date,Qty,Unit"
    # Row 1: Paracetamol tablets converted to strips (8000 / 10 = 800 strips)
    assert "800,strip" in lines[1]
    assert "11/2026" in lines[1]
    # Row 2: Missing batch number defect on index 1
    assert ",11/2026,350,strip" in lines[2]
    # Row 3: Insulin vials (50 vials)
    assert "50,vial" in lines[3]


def test_h3_chat_kannada_english_variants():
    """Verify H3 chat report generates bilingual text mixing Kannada and English."""
    inventory = [
        {"drug_code": "ORS-20", "batch_no": "LOT-ORS-H3-01", "expiry": "2026-12-06", "quantity": 15},
        {"drug_code": "PCM-500", "batch_no": "LOT-PCM-H3-01", "expiry": "2026-12-21", "quantity": 1500},
    ]
    dt = datetime(2026, 11, 1, 9, 30, tzinfo=KOLKATA_TZ)

    msg = generate_chat_report(inventory, dt, seed=42)
    # Check that quantities and dates appear
    assert "15" in msg
    assert ("Yelahanka" in msg or "YLH" in msg or "CHC" in msg)
    # Check that Kannada unicode or English abbreviations are present
    assert any(k in msg for k in ["ಇನ್ಸುಲಿನ್", "ನಮಸ್ಕಾರ", "ದಯವಿಟ್ಟು", "ರೋಗಗಳು", "ಇಲ್ಲ", "sir", "pkt", "sachet"])


def test_h4_messy_register_note_and_bad_data_scenario():
    """Verify H4 handwritten register notes produce typos and bad_data spikes."""
    inventory = [
        {"drug_code": "INS-REG", "batch_no": "LOT-INS-H4-01", "expiry": "2026-11-19", "quantity": 50},
        {"drug_code": "PCM-500", "batch_no": "LOT-PCM-H4-01", "expiry": "2026-12-16", "quantity": 300},
        {"drug_code": "ORS-20", "batch_no": "LOT-ORS-H4-01", "expiry": "2027-01-30", "quantity": 150},
    ]
    dt = datetime(2026, 11, 1, 17, 0, tzinfo=KOLKATA_TZ)

    # Normal messy text
    normal_text = generate_messy_register_note(inventory, dt, bad_data_active=False)
    assert "inzulin" in normal_text
    assert "paracetmol" in normal_text
    assert "50 vials" in normal_text
    assert "1999" not in normal_text

    # bad_data active: must include 10000 inzulin and year 1999
    bad_data_text = generate_messy_register_note(inventory, dt, bad_data_active=True)
    assert "10000 inzulin" in bad_data_text
    assert "1999" in bad_data_text


@pytest.fixture
def hospital_app(monkeypatch):
    monkeypatch.setenv("HOSPITAL_ID", "H1")
    monkeypatch.setenv("USE_FIXTURES", "0")
    monkeypatch.setenv("SQLITE_DB_PATH", ":memory:")
    from sim_hospital import build_app
    return build_app()


@pytest.mark.asyncio
async def test_hospital_api_transfers_and_state(hospital_app):
    """Test inbound/outbound transfer endpoints and ground truth state."""
    async with AsyncClient(
        transport=ASGITransport(app=hospital_app), base_url="http://test"
    ) as client:
        # GET /state
        r_state = await client.get("/state")
        assert r_state.status_code == 200
        state = r_state.json()
        assert state["hospital_id"] == "H1"
        assert state["stock_items_count"] > 0

        initial_ins = [lt for lt in state["inventory"] if lt["drug_code"] == "INS-REG"][0]
        init_qty = initial_ins["quantity"]

        # POST /transfers/inbound
        r_in = await client.post("/transfers/inbound", json={
            "order_id": "DTA/BLR-U/2026/000001",
            "drug_code": "INS-REG",
            "batch_no": initial_ins["batch_no"],
            "expiry": initial_ins["expiry"],
            "quantity": 10,
        })
        assert r_in.status_code == 200
        assert r_in.json()["status"] == "received"

        # Check stock increased
        r_state2 = await client.get("/state")
        ins_after_in = [lt for lt in r_state2.json()["inventory"] if lt["drug_code"] == "INS-REG"][0]
        assert ins_after_in["quantity"] == init_qty + 10

        # POST /transfers/outbound
        r_out = await client.post("/transfers/outbound", json={
            "order_id": "DTA/BLR-U/2026/000002",
            "drug_code": "INS-REG",
            "batch_no": initial_ins["batch_no"],
            "quantity": 5,
        })
        assert r_out.status_code == 200
        assert r_out.json()["status"] == "dispatched"
        assert r_out.json()["remaining_stock"] == init_qty + 5

        # Check FHIR report endpoint
        r_fhir = await client.get("/fhir/InventoryReport")
        assert r_fhir.status_code == 200
        assert r_fhir.json()["resourceType"] == "InventoryReport"

        # Check CSV export endpoint
        r_csv = await client.get("/export/stock.csv")
        assert r_csv.status_code == 200
        assert "Drug Name,Batch No,Exp Date,Qty,Unit" in r_csv.text
