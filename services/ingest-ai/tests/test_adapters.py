"""Tests for all 4 report adapters: FHIR, CSV, Chat, and Text."""

from datetime import date
from pathlib import Path
import pytest

from ingest_ai.adapters.chat import ChatAdapter
from ingest_ai.adapters.csv_adapter import CsvAdapter
from ingest_ai.adapters.fhir import FhirAdapter
from ingest_ai.adapters.text import TextAdapter
from ingest_ai.grounding import GroundingEngine


@pytest.fixture
def grounding():
    return GroundingEngine()


@pytest.mark.asyncio
async def test_fhir_adapter(grounding):
    adapter = FhirAdapter(grounding)
    report_file = Path("evals/golden/raw/fhir/report_01.json")
    with open(report_file, "r", encoding="utf-8") as f:
        content = f.read()

    lots = await adapter.parse(content, facility_code="H1", report_date=date(2026, 11, 1))
    assert len(lots) == 5

    codes = [lt.drug_code for lt in lots]
    assert "INS-REG" in codes
    assert "PCM-500" in codes
    assert "AMOX-500" in codes

    for lt in lots:
        assert lt.confidence == 1.0
        assert lt.expiry is not None
        assert lt.quantity > 0


@pytest.mark.asyncio
async def test_csv_adapter_strip_conversion(grounding):
    adapter = CsvAdapter(grounding)
    report_file = Path("evals/golden/raw/csv/report_01.csv")
    with open(report_file, "r", encoding="utf-8") as f:
        content = f.read()

    lots = await adapter.parse(content, facility_code="H2", report_date=date(2026, 11, 1))
    assert len(lots) == 5

    # Check that missing batch number was automatically handled
    assert any("BATCH-UNSPECIFIED" in (lt.batch_no or "") for lt in lots)

    # Check strip conversion for PCM or AMOX
    pcm_lot = next(lt for lt in lots if lt.drug_code == "PCM-500")
    assert pcm_lot.unit == "tablet"
    assert pcm_lot.quantity >= 10  # strips converted to tablets


@pytest.mark.asyncio
async def test_chat_adapter_bilingual(grounding):
    adapter = ChatAdapter(grounding)
    chat_text = (
        "ನಮಸ್ಕಾರ / Hello sir, Yelahanka CHC stock update for 01/11: "
        "ORS 15 sachets (exp 06/12), Paracetamol 1500 tabs (exp 21/12). "
        "ಇನ್ಸುಲಿನ್ ಇಲ್ಲ (no insulin in stock). Please arrange emergency supply."
    )

    lots = await adapter.parse(chat_text, facility_code="H3", report_date=date(2026, 11, 1))
    assert len(lots) >= 2

    ors_lot = next((lt for lt in lots if lt.drug_code == "ORS-20"), None)
    assert ors_lot is not None
    assert ors_lot.quantity == 15
    assert ors_lot.expiry == date(2026, 12, 6)

    pcm_lot = next((lt for lt in lots if lt.drug_code == "PCM-500"), None)
    assert pcm_lot is not None
    assert pcm_lot.quantity == 1500
    assert pcm_lot.expiry == date(2026, 12, 21)

    # Zero stock insulin handled
    ins_lot = next((lt for lt in lots if lt.drug_code == "INS-REG"), None)
    assert ins_lot is not None
    assert ins_lot.quantity == 0


@pytest.mark.asyncio
async def test_text_adapter_normal_and_anomaly(grounding):
    adapter = TextAdapter(grounding)

    # Normal text
    normal_text = """DAILY STOCK REGISTER - HESARAGHATTA PHC
Date: 01/11/2026
Physical count taken at ILR & ambient rack:
---------------------------------------------------------
inzulin reg 100iu: 50 vials b.no LOT-INS-H4-01 exp 2026-11-19
paracetmol 500mg: 300 tab b.no LOT-PCM-H4-01 exp 2026-12-16
ors sachet 20.5g: 150 pkt b.no LOT-ORS-H4-01 exp 2027-01-30
---------------------------------------------------------
"""
    lots = await adapter.parse(normal_text, facility_code="H4", report_date=date(2026, 11, 1))
    assert len(lots) == 3

    ins = next(lt for lt in lots if lt.drug_code == "INS-REG")
    assert ins.quantity == 50
    assert ins.batch_no == "LOT-INS-H4-01"
    assert ins.expiry == date(2026, 11, 19)

    # Bad data text with 10,000 vials and year 1999
    bad_text = """DAILY STOCK REGISTER - HESARAGHATTA PHC
Date: 01/11/2026
---------------------------------------------------------
10000 inzulin reg 100iu vials b.no B-999 exp 14/08/1999
paracetmol 500mg tabs: 300 tab b.no LOT-PCM-H4-01 exp 2026-12-16
---------------------------------------------------------
"""
    bad_lots = await adapter.parse(bad_text, facility_code="H4", report_date=date(2026, 11, 1))
    assert len(bad_lots) == 2

    bad_ins = next(lt for lt in bad_lots if lt.drug_code == "INS-REG")
    assert bad_ins.quantity == 10000
    assert bad_ins.batch_no == "B-999"
    assert bad_ins.expiry == date(1999, 8, 14)
