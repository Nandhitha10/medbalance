"""Core API Service entrypoint."""

from medbal_common.fastapi_base import create_app
from medbal_common import fixtures

app = create_app(name="core-api", title="MedBalance Core API")
fixtures.serve(app, "core-api")
