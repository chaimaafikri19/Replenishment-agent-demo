"""
Saves a snapshot of the API's data to frontend/demo-data.json, so the
dashboard can run as a static site (demo mode) with no API.

Run it from the project folder whenever the data changes:
    .venv/bin/python scripts/export_demo_data.py
"""

import json
import sys
from datetime import date
from pathlib import Path

# Let this script import the backend package from the project folder.
PROJECT_FOLDER = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_FOLDER))

from backend.main import get_agent_suggestions, get_stock, get_suppliers  # noqa: E402

OUTPUT_FILE = PROJECT_FOLDER / "frontend" / "demo-data.json"


def main():
    # Call the same functions the API endpoints use, so the data is identical.
    snapshot = {
        "snapshot_date": date.today().isoformat(),
        "stock": get_stock(),
        "suppliers": get_suppliers(),
        "agent_suggestions": get_agent_suggestions(),
    }
    OUTPUT_FILE.write_text(json.dumps(snapshot, indent=2) + "\n")
    print(f"Saved {OUTPUT_FILE.relative_to(PROJECT_FOLDER)} "
          f"({len(snapshot['stock'])} products, {len(snapshot['agent_suggestions'])} suggestions)")


if __name__ == "__main__":
    main()
