"""Ingest-AI Service entrypoint."""

from medbal_common.fastapi_base import create_app
from medbal_common import fixtures

app = create_app(name="ingest-ai", title="MedBalance Ingest AI")
fixtures.serve(app, "ingest-ai")
