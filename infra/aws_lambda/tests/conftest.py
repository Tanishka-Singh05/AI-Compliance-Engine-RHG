import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
for _p in (ROOT, os.path.join(ROOT, "services")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
