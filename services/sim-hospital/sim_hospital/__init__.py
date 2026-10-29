"""Top-level package exposure for sim_hospital."""

from sim_hospital.db import HospitalDB
from sim_hospital.hospital import HospitalNode
from sim_hospital.main import build_app, app
from sim_hospital.styles.chat import generate_chat_report
from sim_hospital.styles.csv_export import generate_stock_csv
from sim_hospital.styles.fhir import generate_fhir_inventory_report
from sim_hospital.styles.messy_text import generate_messy_register_note

__all__ = [
    "HospitalDB",
    "HospitalNode",
    "build_app",
    "app",
    "generate_chat_report",
    "generate_stock_csv",
    "generate_fhir_inventory_report",
    "generate_messy_register_note",
]

