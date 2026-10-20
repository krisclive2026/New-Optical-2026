"""
App metadata helpers -- currently just the "launch counter" shown on
the About screen (mirrors the "successfully running N times" line
used across KRISC products).

The counter lives in a tiny text file inside databases/ so it survives
restarts but stays independent of the SQLAlchemy models/migrations.
"""
import os

from config import DB_DIR

RUN_COUNT_FILE = os.path.join(DB_DIR, 'run_count.txt')

APP_NAME = "VisionCraft"
APP_TAGLINE = "Optical Store Management Software"
DEVELOPER_NAME = "KriscSoft"
DEVELOPER_CONTACT = "9894295732"


def get_run_count() -> int:
    """Current launch count without incrementing it."""
    if not os.path.exists(RUN_COUNT_FILE):
        return 0
    try:
        with open(RUN_COUNT_FILE, 'r') as f:
            return int(f.read().strip() or 0)
    except (ValueError, OSError):
        return 0


def increment_run_count() -> int:
    """Bump the launch counter by 1 and return the new total.

    Called once per app start (see create_app()) so it counts
    "times the application has been run", not individual requests.
    """
    count = get_run_count() + 1
    os.makedirs(DB_DIR, exist_ok=True)
    try:
        with open(RUN_COUNT_FILE, 'w') as f:
            f.write(str(count))
    except OSError:
        pass
    return count
