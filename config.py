import os
import sys

APP_FOLDER_NAME = 'VisionCraft'

# Where the app itself is installed/extracted from -- used only for
# static assets (templates/static) that ship inside the exe, never for
# writable data.
if getattr(sys, 'frozen', False):
    BASE_DIR = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
else:
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _writable_data_dir():
    """Where the database/license/run-counter live.

    Uses the OS's per-user app-data folder so the data survives the exe
    being moved, reinstalled, or updated -- rather than living next to
    the exe itself. Windows: %APPDATA%\\VisionCraft
    macOS: ~/Library/Application Support/VisionCraft
    Linux: ~/.local/share/VisionCraft
    """
    if sys.platform == 'win32':
        root = os.environ.get('APPDATA') or os.path.expanduser('~')
    elif sys.platform == 'darwin':
        root = os.path.expanduser('~/Library/Application Support')
    else:
        root = os.environ.get('XDG_DATA_HOME') or os.path.expanduser('~/.local/share')
    return os.path.join(root, APP_FOLDER_NAME)


DB_DIR = _writable_data_dir()

if not os.path.exists(DB_DIR):
    os.makedirs(DB_DIR)

UPLOAD_FOLDER = os.path.join(DB_DIR, 'uploads')
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

class Config:
    SECRET_KEY = SECRET_KEY = os.environ.get('SECRET_KEY')
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(DB_DIR, 'optical_store.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = UPLOAD_FOLDER
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max image upload size
    STORE_NAME = "VisionCraft Optical & Eye Care"
    STORE_ADDRESS = "123 Specs Avenue, ClearVision Plaza, City Center"
    STORE_PHONE = "+1 (555) 019-2834"
    STORE_EMAIL = "contact@visioncraftoptical.com"
