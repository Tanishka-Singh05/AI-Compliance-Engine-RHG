"""AWS Lambda entrypoint for the ACE scan API.

OPA is a shared/remote service reached through the ``OPA_URL`` environment
variable; this handler does not start an OPA server in-process. When OPA is
unreachable the API fails closed (``503`` from ``/ace/scan``; agent/gate paths
block).
"""

from mangum import Mangum

from ace.main import app

handler = Mangum(app, lifespan="off")
