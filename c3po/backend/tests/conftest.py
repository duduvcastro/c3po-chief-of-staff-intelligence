from __future__ import annotations

import os


# Test modules import the FastAPI application during collection. Force the
# in-memory database before those imports so a production container can never
# let pytest inherit its PostgreSQL credential and overwrite live snapshots.
os.environ["C3PO_DATABASE_URL"] = ""
os.environ["DATABASE_URL"] = ""
os.environ["C3PO_AUTH_COOKIE_SECURE"] = "false"
os.environ["C3PO_BRAPI_TOKEN"] = ""
os.environ["BRAPI_TOKEN"] = ""
os.environ["C3PO_EODHD_API_TOKEN"] = ""
os.environ["EODHD_API_TOKEN"] = ""
os.environ["C3PO_PLUGGY_CLIENT_ID"] = ""
os.environ["PLUGGY_CLIENT_ID"] = ""
os.environ["C3PO_PLUGGY_CLIENT_SECRET"] = ""
os.environ["PLUGGY_CLIENT_SECRET"] = ""
os.environ["C3PO_PLUGGY_ITEM_IDS"] = ""
os.environ["PLUGGY_ITEM_IDS"] = ""
