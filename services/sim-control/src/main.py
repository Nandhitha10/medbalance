"""Sim-Control Service entrypoint."""

from medbal_common.fastapi_base import create_app
from medbal_common import fixtures

app = create_app(name="sim-control", title="MedBalance Simulation Control")
fixtures.serve(app, "sim-control")
