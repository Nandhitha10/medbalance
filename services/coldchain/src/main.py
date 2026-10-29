"""ColdChain Service entrypoint."""

from medbal_common.fastapi_base import create_app
from medbal_common import fixtures

app = create_app(name="coldchain", title="MedBalance ColdChain Monitoring")
fixtures.serve(app, "coldchain")
