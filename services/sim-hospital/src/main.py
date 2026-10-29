"""Simulated Hospital Node entrypoint."""

import os
from medbal_common.fastapi_base import create_app
from medbal_common import fixtures

hospital_id = os.getenv("HOSPITAL_ID", "H1").upper()
app = create_app(
    name=f"sim-hospital-{hospital_id.lower()}",
    title=f"MedBalance Simulated Hospital {hospital_id}",
)
fixtures.serve(app, "sim-hospital")
