"""
KRISC License Manager
----------------------
Handles machine identification, System ID generation, license-key
verification and local license storage for the VisionCraft OSMS app.

How it works
------------
1. On first run the app computes a "System ID" from this machine's
   hardware ID plus today's date and shows it on the /license page.
2. The user sends that System ID to KRISC. The developer pastes it
   into the separate `keygen_tool.py` (kept private, never shipped
   to customers), picks an expiry date, and generates a License Key.
3. The user pastes the License Key back into the /license page.
   This module verifies the key's RSA-PSS signature against the
   public key below, checks it was issued for *this* machine, and
   checks the expiry date.
4. The verified license (machine id + expiry) is cached locally in
   databases/license.lic. Every request re-checks expiry, so an
   expired license automatically drops the user back to the
   activation/renewal page.

Only the PUBLIC key lives in this file -- it can verify signatures
but cannot create them, so shipping this file to a customer does not
let them mint their own keys.
"""
import base64
import hashlib
import json
import os
import platform
import uuid
from datetime import datetime

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from config import DB_DIR

LICENSE_FILE = os.path.join(DB_DIR, 'license.lic')

# Public half of the KRISC signing keypair. The matching private key
# lives ONLY in keygen_tool.py on the developer's machine and must
# never be committed to a customer-facing build.
PUBLIC_KEY_PEM = b"""-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA0AHr6I0f17qriZiv7VdZ
r8XE8Ppx5g/ANkOZFrhD+UaTPJzWBsmKQiZ6hhTuAT8H3IUQYB1oWFqFM5oaL57m
YfX6UC/XBl462s9H8iP8gUSLdvaXkMz2MlzBilFUeGETR/CuCLTeNUj5wqTVl9Kf
e4AGqPAG5cc+jcZ+PT3RtCA2ffdswTPcGgFa4Vk2a4TmCRwxYz1l6EdyWi0p6+bL
bmVsw5VIBB4EsMmGLhEWLZ1AxV7JBhAbWTYb4eGCTbSvRFDnB4CowSZUH0KBJmHo
1VELOl67THfJIYb1GysYs+ByImF9no8yYlWgmUMb7ZhDGxY3b3oWzmvx4P2BBVZU
swIDAQAB
-----END PUBLIC KEY-----
"""

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I, easy to type


def _b32_encode(raw: bytes) -> str:
    """Encode bytes into a Crockford-ish, human-typeable base32 string."""
    bits = int.from_bytes(raw, 'big')
    total_chars = (len(raw) * 8 + 4) // 5
    chars = []
    for _ in range(total_chars):
        chars.append(_ALPHABET[bits & 0x1F])
        bits >>= 5
    return ''.join(reversed(chars))


def _group(s: str, size: int = 5) -> str:
    return '-'.join(s[i:i + size] for i in range(0, len(s), size))


# ---------------------------------------------------------------------
# Machine identity
# ---------------------------------------------------------------------
def _raw_hardware_id() -> str:
    """The OS's own persistent per-install identifier, when available.

    These survive reboots, network changes and hostname renames far
    more reliably than a MAC address (uuid.getnode() can even return
    a random value each run on machines with no real NIC to read).
    Falls back to a MAC + hostname combo only if nothing else works.
    """
    system = platform.system()
    try:
        if system == 'Windows':
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography")
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
            if value:
                return value
        elif system == 'Darwin':
            import subprocess
            out = subprocess.check_output(
                ['ioreg', '-rd1', '-c', 'IOPlatformExpertDevice'], text=True, stderr=subprocess.DEVNULL
            )
            for line in out.splitlines():
                if 'IOPlatformUUID' in line:
                    return line.split('=')[-1].strip().strip('"')
        elif system == 'Linux':
            for path in ('/etc/machine-id', '/var/lib/dbus/machine-id'):
                if os.path.exists(path):
                    with open(path) as f:
                        value = f.read().strip()
                    if value:
                        return value
    except Exception:
        pass
    # Fallback for anything unhandled or where the above failed.
    return f"{uuid.getnode()}|{platform.node()}|{system}"


def get_machine_id() -> str:
    """A short, stable-per-machine fingerprint (hex, 16 chars)."""
    return hashlib.sha256(_raw_hardware_id().encode()).hexdigest()[:16]


def generate_system_id() -> str:
    """System ID = machine id + today's date, packed and encoded.

    Format shown to the user: XXXXX-XXXXX-XXXXX-XXXXX (grouped for
    easy reading/typing). The embedded date is informational (lets
    the developer see when the request was made); only the machine
    id portion is used to bind the eventual license key.
    """
    machine_id = get_machine_id()
    date_str = datetime.now().strftime('%y%m%d')  # 6 digits, for reference only
    return _format_system_id(machine_id, date_str)


def _format_system_id(machine_id: str, date_str: str) -> str:
    body = _b32_encode(bytes.fromhex(machine_id))  # 16 hex chars -> ~26 b32 chars
    full = (body + date_str).upper()
    return _group(full, 5)


def parse_system_id(system_id: str):
    """Reverse of _format_system_id. Returns (machine_id_hex, date_str) or None."""
    try:
        cleaned = system_id.replace('-', '').replace(' ', '').strip().upper()
        date_str = cleaned[-6:]
        body = cleaned[:-6]
        # Recover the 16-hex-char machine id from its base32 body
        bits = 0
        for ch in body:
            bits = (bits << 5) | _ALPHABET.index(ch)
        num_bytes = (len(body) * 5) // 8
        raw = bits.to_bytes(num_bytes, 'big')
        machine_id = raw[:8].hex()
        return machine_id, date_str
    except Exception:
        return None


# ---------------------------------------------------------------------
# License key creation (signature side -- mirrors keygen_tool.py so
# both stay in sync; the actual signing only ever happens in the
# separate keygen tool, which holds the private key).
# ---------------------------------------------------------------------
def _license_payload(machine_id: str, expiry_date: str) -> bytes:
    """Canonical bytes that get signed / verified.
    expiry_date must be 'YYYY-MM-DD'.
    """
    data = {"m": machine_id, "e": expiry_date}
    return json.dumps(data, sort_keys=True, separators=(',', ':')).encode()


def verify_license_key(license_key: str):
    """Verify a license key string against this machine's id.

    Returns a dict {'valid': bool, 'expiry_date': str|None, 'error': str|None}.
    """
    try:
        raw = base64.urlsafe_b64decode(_pad_b64(license_key.strip().replace(' ', '').replace('\n', '')))
        obj = json.loads(raw.decode())
        machine_id = obj['m']
        expiry_date = obj['e']
        signature = base64.urlsafe_b64decode(_pad_b64(obj['sig']))
    except Exception:
        return {'valid': False, 'expiry_date': None, 'error': 'That license key is not formatted correctly.'}

    public_key = serialization.load_pem_public_key(PUBLIC_KEY_PEM)
    payload = _license_payload(machine_id, expiry_date)
    try:
        public_key.verify(
            signature,
            payload,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256(),
        )
    except InvalidSignature:
        return {'valid': False, 'expiry_date': None, 'error': 'Invalid license key signature.'}

    if machine_id != get_machine_id():
        return {'valid': False, 'expiry_date': None, 'error': 'This license key was issued for a different computer.'}

    try:
        expiry = datetime.strptime(expiry_date, '%Y-%m-%d').date()
    except ValueError:
        return {'valid': False, 'expiry_date': None, 'error': 'This license key has an invalid expiry date.'}

    if expiry < datetime.now().date():
        return {'valid': False, 'expiry_date': expiry_date, 'error': 'This license has expired. Please renew it.'}

    return {'valid': True, 'expiry_date': expiry_date, 'error': None}


def _pad_b64(s: str) -> str:
    return s + '=' * (-len(s) % 4)


# ---------------------------------------------------------------------
# Local persistence
# ---------------------------------------------------------------------
def save_license(license_key: str) -> None:
    os.makedirs(DB_DIR, exist_ok=True)
    with open(LICENSE_FILE, 'w') as f:
        f.write(license_key.strip())


def _load_raw_key():
    if not os.path.exists(LICENSE_FILE):
        return None
    with open(LICENSE_FILE, 'r') as f:
        key = f.read().strip()
    return key or None


def get_license_status() -> dict:
    """Single entry point the app uses on every request.

    Returns:
        {
          'activated': bool,   # a key is present and currently valid
          'expiry_date': str | None,
          'days_left': int | None,
          'error': str | None, # reason it's not activated, if any
        }
    """
    key = _load_raw_key()
    if not key:
        return {'activated': False, 'expiry_date': None, 'days_left': None, 'error': 'No license activated yet.'}

    result = verify_license_key(key)
    if not result['valid']:
        return {'activated': False, 'expiry_date': result['expiry_date'], 'days_left': None, 'error': result['error']}

    expiry = datetime.strptime(result['expiry_date'], '%Y-%m-%d').date()
    days_left = (expiry - datetime.now().date()).days
    return {'activated': True, 'expiry_date': result['expiry_date'], 'days_left': days_left, 'error': None}
