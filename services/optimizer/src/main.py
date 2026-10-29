"""Optimizer Service entrypoint."""

from medbal_common.fastapi_base import create_app
from medbal_common import fixtures

app = create_app(name="optimizer", title="MedBalance QUBO Optimizer")
fixtures.serve(app, "optimizer")

