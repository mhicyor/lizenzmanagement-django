"""An additional database-level write barrier for the public demo process."""
import os
import sqlite3
from pathlib import Path


def connect(database, *args, **kwargs):
    if os.environ.get("DEMO_READ_ONLY") == "1":
        database = Path(database).resolve().as_uri() + "?mode=ro"
        kwargs["uri"] = True
    return sqlite3.connect(database, *args, **kwargs)
