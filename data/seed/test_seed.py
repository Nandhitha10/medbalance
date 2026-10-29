"""Tests for deterministic district seed generator and story invariants."""

from datetime import date
import json
from pathlib import Path
import sys
import pytest
import yaml

DATA_SEED_DIR = Path(__file__).resolve().parent
ROOT_DIR = DATA_SEED_DIR.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from data.seed.generate import generate_seed

DB_INIT_DIR = ROOT_DIR / "db" / "init"
HOSPITALS_DIR = DATA_SEED_DIR / "hospitals"



@pytest.fixture(scope="module", autouse=True)
def run_generator():
    """Ensure seed generation runs with seed 42 before tests."""
    generate_seed(seed_val=42)


def test_generator_determinism(tmp_path):
    """Verify that generating with the same seed is 100% deterministic."""
    sql_path = DB_INIT_DIR / "002_seed.sql"
    content_run1 = sql_path.read_text(encoding="utf-8")

    generate_seed(seed_val=42)
    content_run2 = sql_path.read_text(encoding="utf-8")

    assert content_run1 == content_run2, "Seed generation is not deterministic!"


def test_facilities_loaded_correctly():
    """Verify facilities configuration in district.yaml."""
    with open(DATA_SEED_DIR / "district.yaml", "r", encoding="utf-8") as f:
        district_data = yaml.safe_load(f)

    facilities = district_data["facilities"]
    assert len(facilities) == 5

    levels = {fac["level"] for fac in facilities}
    assert levels == {"DH", "TH", "CHC", "PHC", "WH"}

    # H4 cold storage check
    h4 = [fac for fac in facilities if fac["id"] == "H4"][0]
    assert h4["cold_storage_ok"] is False
    assert "ILR under repair" in h4.get("cold_storage_note", "")


def test_drugs_and_aliases_loaded():
    """Verify drugs configuration in drugs.yaml including Kannada aliases."""
    with open(DATA_SEED_DIR / "drugs.yaml", "r", encoding="utf-8") as f:
        drugs_data = yaml.safe_load(f)

    drugs = drugs_data["drugs"]
    assert len(drugs) == 13, f"Expected 13 drugs, found {len(drugs)}"

    drug_codes = {d["code"] for d in drugs}
    assert "INS-REG" in drug_codes
    assert "OXY-10" in drug_codes
    assert "ASV-10" in drug_codes
    assert "TD-VAC" in drug_codes
    assert "CEFT-1000" in drug_codes
    assert "RL-500" in drug_codes
    assert "ORS-20" in drug_codes
    assert "PCM-500" in drug_codes
    assert "AMOX-500" in drug_codes
    assert "MET-500" in drug_codes
    assert "AML-5" in drug_codes
    assert "IFA-W" in drug_codes
    assert "MOR-10" in drug_codes

    # Check morphine is controlled
    mor = [d for d in drugs if d["code"] == "MOR-10"][0]
    assert mor.get("is_controlled") is True

    # Check Kannada aliases
    ins = [d for d in drugs if d["code"] == "INS-REG"][0]
    kannada_aliases = [a["alias"] for a in ins.get("aliases", []) if a.get("language") == "kn"]
    assert "ಇನ್ಸುಲಿನ್" in kannada_aliases

    pcm = [d for d in drugs if d["code"] == "PCM-500"][0]
    kannada_pcm = [a["alias"] for a in pcm.get("aliases", []) if a.get("language") == "kn"]
    assert "ಪ್ಯಾರಸಿಟಮಾಲ್" in kannada_pcm

    ors = [d for d in drugs if d["code"] == "ORS-20"][0]
    kannada_ors = [a["alias"] for a in ors.get("aliases", []) if a.get("language") == "kn"]
    assert "ಒಆರ್‌ಎಸ್" in kannada_ors


def test_story_invariants_in_hospital_json():
    """Verify that each hospital's JSON file contains the engineered story lots."""
    # 1. H4: 50 vials of insulin expiring in ~18 days
    h4_path = HOSPITALS_DIR / "h4.json"
    assert h4_path.exists()
    with open(h4_path, "r", encoding="utf-8") as f:
        h4_data = json.load(f)

    assert h4_data["hospital_id"] == "H4"
    assert h4_data["cold_storage_ok"] is False

    insulin_lots_h4 = [
        item for item in h4_data["inventory"] if item["drug_code"] == "INS-REG"
    ]
    assert len(insulin_lots_h4) == 1
    h4_ins = insulin_lots_h4[0]
    assert h4_ins["quantity"] == 50
    assert h4_ins["batch_no"] == "LOT-INS-H4-01"

    # Expiry window ~18 days from 2026-11-01
    expiry_date = date.fromisoformat(h4_ins["expiry"])
    anchor_date = date(2026, 11, 1)
    delta_days = (expiry_date - anchor_date).days
    assert 15 <= delta_days <= 20, f"Expected expiry ~18 days, got {delta_days} days"

    # 2. H1: Near-zero insulin and oxytocin
    h1_path = HOSPITALS_DIR / "h1.json"
    with open(h1_path, "r", encoding="utf-8") as f:
        h1_data = json.load(f)

    h1_ins = [item for item in h1_data["inventory"] if item["drug_code"] == "INS-REG"]
    assert len(h1_ins) == 1
    assert h1_ins[0]["quantity"] <= 5, "H1 should have near-zero insulin"

    h1_oxy = [item for item in h1_data["inventory"] if item["drug_code"] == "OXY-10"]
    assert len(h1_oxy) == 1
    assert h1_oxy[0]["quantity"] <= 5, "H1 should have near-zero oxytocin"

    # 3. H2: Over-stocked IFA, PCM, amoxicillin near expiry; 1 morphine lot (F6 demo)
    h2_path = HOSPITALS_DIR / "h2.json"
    with open(h2_path, "r", encoding="utf-8") as f:
        h2_data = json.load(f)

    h2_ifa = [item for item in h2_data["inventory"] if item["drug_code"] == "IFA-W"][0]
    assert h2_ifa["quantity"] >= 10000, "H2 should be over-stocked on IFA"

    h2_pcm = [item for item in h2_data["inventory"] if item["drug_code"] == "PCM-500"][0]
    assert h2_pcm["quantity"] >= 5000, "H2 should be over-stocked on PCM"

    h2_amx = [item for item in h2_data["inventory"] if item["drug_code"] == "AMOX-500"][0]
    assert h2_amx["quantity"] >= 2000, "H2 should be over-stocked on Amoxicillin"

    h2_mor = [item for item in h2_data["inventory"] if item["drug_code"] == "MOR-10"]
    assert len(h2_mor) == 1, "H2 should have a morphine lot for F6 rule check"
    assert h2_mor[0]["quantity"] > 0

    # 4. H3: Low ORS before dengue scenario
    h3_path = HOSPITALS_DIR / "h3.json"
    with open(h3_path, "r", encoding="utf-8") as f:
        h3_data = json.load(f)

    h3_ors = [item for item in h3_data["inventory"] if item["drug_code"] == "ORS-20"][0]
    assert h3_ors["quantity"] <= 30, "H3 should have low ORS stock"


def test_all_lot_quantities_non_negative():
    """Verify that every generated lot has quantity >= 0."""
    for hosp_file in HOSPITALS_DIR.glob("*.json"):
        with open(hosp_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        for lot in data.get("inventory", []):
            assert lot["quantity"] >= 0, f"Negative lot quantity in {hosp_file}: {lot}"


def test_sql_seed_file_integrity():
    """Verify that 002_seed.sql exists and contains expected insert blocks."""
    sql_path = DB_INIT_DIR / "002_seed.sql"
    assert sql_path.exists()
    content = sql_path.read_text(encoding="utf-8")

    assert "INSERT INTO facility" in content
    assert "INSERT INTO drug" in content
    assert "INSERT INTO drug_alias" in content
    assert "INSERT INTO vehicle" in content
    assert "INSERT INTO route" in content
    assert "INSERT INTO policy" in content
    assert "INSERT INTO consumption_daily" in content
    assert "INSERT INTO lot" in content
    assert "COMMIT;" in content
