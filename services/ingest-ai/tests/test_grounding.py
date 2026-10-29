"""Tests for RapidFuzz drug entity grounding across typos and Kannada script."""

import pytest
from ingest_ai.grounding import GroundingEngine


@pytest.fixture
def grounding():
    return GroundingEngine()


def test_grounding_exact_code(grounding):
    matches = grounding.match_mention("INS-REG", top_k=3)
    assert len(matches) > 0
    assert matches[0].drug_code == "INS-REG"
    assert matches[0].score >= 0.95


def test_grounding_english_typos(grounding):
    # Typo: inzulin -> INS-REG
    ins_matches = grounding.match_mention("inzulin", top_k=3)
    assert len(ins_matches) > 0
    assert ins_matches[0].drug_code == "INS-REG"
    assert ins_matches[0].score >= 0.85

    # Typo: paracetmol -> PCM-500
    pcm_matches = grounding.match_mention("paracetmol", top_k=3)
    assert len(pcm_matches) > 0
    assert pcm_matches[0].drug_code == "PCM-500"
    assert pcm_matches[0].score >= 0.85

    # Shorthand: amoxy -> AMOX-500
    amx_matches = grounding.match_mention("amoxy", top_k=3)
    assert len(amx_matches) > 0
    assert amx_matches[0].drug_code == "AMOX-500"


def test_grounding_kannada_script(grounding):
    # Kannada: ಇನ್ಸುಲಿನ್ (Insulin) -> INS-REG
    kn_ins = grounding.match_mention("ಇನ್ಸುಲಿನ್", top_k=3)
    assert len(kn_ins) > 0
    assert kn_ins[0].drug_code == "INS-REG"
    assert kn_ins[0].score >= 0.90

    # Kannada: ಪ್ಯಾರಸಿಟಮಾಲ್ (Paracetamol) -> PCM-500
    kn_pcm = grounding.match_mention("ಪ್ಯಾರಸಿಟಮಾಲ್", top_k=3)
    assert len(kn_pcm) > 0
    assert kn_pcm[0].drug_code == "PCM-500"
    assert kn_pcm[0].score >= 0.90

    # Kannada: ಒಆರ್‌ಎಸ್ (ORS) -> ORS-20
    kn_ors = grounding.match_mention("ಒಆರ್‌ಎಸ್", top_k=3)
    assert len(kn_ors) > 0
    assert kn_ors[0].drug_code == "ORS-20"


def test_extract_candidate_drug_codes(grounding):
    text = "Sir YLH CHC pharmacy report: PCM 500mg 1500 nos, ORS 15 pkt, Amoxicillin 600 tabs. ಇನ್ಸುಲಿನ್ ಇಲ್ಲ."
    candidates = grounding.extract_candidates_for_text(text, top_k=5)
    assert "PCM-500" in candidates
    assert "ORS-20" in candidates
    assert "AMOX-500" in candidates
    assert "INS-REG" in candidates
