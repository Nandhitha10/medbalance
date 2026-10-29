"""GenAI Service entrypoint."""

from medbal_common.fastapi_base import create_app
from medbal_common import fixtures

app = create_app(name="genai", title="MedBalance GenAI Gateway")
fixtures.serve(app, "genai")

