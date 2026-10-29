"""Forecast Service entrypoint."""

from medbal_common.fastapi_base import create_app
from medbal_common import fixtures

app = create_app(name="forecast", title="MedBalance Forecast Service")
fixtures.serve(app, "forecast")
