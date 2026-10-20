"""
KRISC License Key Generator -- DEVELOPER TOOL, DO NOT SHIP TO CUSTOMERS
=========================================================================
Run this on your own machine. It holds the PRIVATE signing key
(krisc_license_private.pem) and is the only place license keys can be
minted -- the customer's copy of the app only ever gets the public key
(see utils/license_manager.py), so it can verify keys but never forge
them.

Workflow
--------
1. Customer opens the app, goes to Settings > License, and sends you
   the "System ID" shown there (it encodes their machine + the date
   they requested it).
2. Paste that System ID below and click "Parse".
3. Pick (or type) an expiry date.
4. Click "Generate License Key" and send the resulting key back to
   the customer -- they paste it into the app's License page to
   activate.

Requires: `pip install cryptography` (same as the main app).
"""
import base64
import json
import os
import sys
import tkinter as tk
from datetime import date, timedelta
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from utils.license_manager import parse_system_id, _license_payload, PUBLIC_KEY_PEM

# The signing key is built into this tool, so no .pem file is needed next to it.
# !! This file now CONTAINS THE PRIVATE KEY. Keep keygen_tool.py (and any .exe
# !! built from it) on YOUR machine only -- never ship it to a customer.
EMBEDDED_PRIVATE_KEY_PEM = b"""-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQDQAevojR/XuquJ
mK/tV1mvxcTw+nHmD8A2Q5kWuEP5RpM8nNYGyYpCJnqGFO4BPwfchRBgHWhYWoUz
mhovnuZh9fpQL9cGXjraz0fyI/yBRIt29peQzPYyXMGKUVR4YRNH8K4ItN41SPnC
pNWX0p97gAao8Ablxz6Nxn49PdG0IDZ992zBM9waAVrhWTZrhOYJHDFjPWXoR3Ja
LSnr5stuZWzDlUgEHgSwyYYuERYtnUDFXskGEBtZNhvh4YJNtK9EUOcHgKjBJlQf
QoEmYejVUQs6XrtMd8khhvUbKxiz4HIiYX2ejzJiVaCZQxvtmEMbFjdvehbOa/Hg
/YEFVlSzAgMBAAECggEACp8Wf0T5i8gF61xHG3z64O1d3ZpER6WlQIAaKJ1XJzrx
2MX/bdBLxY32crNN5fVkft+ykt3djqlspNJpJOZdyEHJut9+gN497h9ogpZQ1f78
iiIUYjn9FlxDK790a0M1u1YwZNRrhlgIHObS21JPf3xtmqHLEF+os4+fsZvfAe4N
i2gsJ6Q46I5kqzDycUWt3gXkmYNJD5Xw5uGlueQM03hTEO8TEXooNUP+cyDuqSp1
Z0hg8X13sXR+L5nyzQ5PFy1QUZxOlY+NCa8gahdjPHfWihS4WBBibxkUL+8+eHvX
3PMWMkAORGRWslhR5PGfakQgC9v0hMZnQfmpJWzxKQKBgQD24+0pSq2/CWRBgjsX
s9CJdljDE9cat7X30rqL8uyC/Z95fMmtqK94LIAvILdOKLpDhecIHqiV3Bjmpdxr
SsU0V+HOigqU8URB+pTKI/dYLh1BfYAGpKzyDbsEICpWeRKfbj4I6TRX1D7PDiZs
P875PPhASiOcpvbQSntfmsxR+wKBgQDXrrdVzGbv1VfQKBtbGIqfEpwQOZtDSDS5
2DnFXbRFVz/sXznCee/uSXG25QHTLiXrZ8x+70CR7PCPiG5R8+UuFSNc9iB/6eHL
q7kRONJFY+qxm+Eoy7DK9CnvcxJSfLibS/2UC/grkfuAhKWPkV20g5317E79XlnH
3YEqPrzCqQKBgDCYxMHv9Ss5Sgaq/762okGsjeQ4L4sOxj61uAp8EpnmGlHrgjcw
kPlyqPid0/cKhT9tSACNKFn3LN+Znj1wRkj7U3M4MMUIiIsEK+1uDu3IhfGyJlUo
bPJoSXuSaUMEKeo/5O4UGT2Ahaxz+JQuKytcGPFupnvbUZHGV2qGKdmpAoGAM7zk
m79JnhSWWQeV8FdFwXzsVPQMq6ohg8c7rH2a5dtVKTV6nI01ofqaPZ5XvrnePMcM
hhKMcbTdzACVPjF8c358misshqKrGHlcDqaLwjuCrBJRg8DA6x6BBMCcz469lfs3
nBD2+jStmRm4wWTEjq3X8Ys7M4ozjT80Ydbk3ukCgYEAgb3nOGu4gfdCy5ZCUmcf
KZxcUeeAjYu5aTA4+beGIFVaz00tmW++QQV/vVxO6/rgNtQtYoFsaIkmMBg8q4O7
hUU6us5Onq/iMoGwqjV4VaC3eDVaZ5J3bUjdCf2d73TFP5xDyF/2rOwZGSLeuNOK
7gooi+Ykc3a6bk7wEpL1OLo=
-----END PRIVATE KEY-----
"""

KEY_FILENAME = 'krisc_license_private.pem'
# Kept for backwards compatibility with anything that imports it.
PRIVATE_KEY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), KEY_FILENAME)


def _candidate_paths():
    """Places the private key is looked for, in order."""
    dirs = [os.path.dirname(os.path.abspath(__file__))]
    if getattr(sys, 'frozen', False):          # running as a packaged .exe
        dirs.append(os.path.dirname(sys.executable))
    dirs.append(os.getcwd())                    # folder the tool was launched from
    seen, paths = set(), []
    for d in dirs:
        p = os.path.join(d, KEY_FILENAME)
        if p not in seen:
            seen.add(p)
            paths.append(p)
    return paths


def load_private_key(path=None):
    """Load the signing key. Returns (private_key, path_used).

    Also checks the key really is the partner of the public key built into
    utils/license_manager.py -- keys signed with any other private key would
    be rejected by the customer's app as 'Invalid license key signature'.
    """
    if path is None and EMBEDDED_PRIVATE_KEY_PEM.strip():
        pem_bytes, path = EMBEDDED_PRIVATE_KEY_PEM, "(built into this tool)"
    else:
        if path is None:
            tried = _candidate_paths()
            path = next((p for p in tried if os.path.exists(p)), None)
            if path is None:
                raise FileNotFoundError(
                    f"{KEY_FILENAME} not found. Looked in:\n  " + "\n  ".join(tried) +
                    "\nCopy the file next to keygen_tool.py, or use 'Browse for private key...'."
                )
        with open(path, 'rb') as f:
            pem_bytes = f.read()
    key = serialization.load_pem_private_key(pem_bytes, password=None)

    fmt = dict(encoding=serialization.Encoding.DER, format=serialization.PublicFormat.SubjectPublicKeyInfo)
    if key.public_key().public_bytes(**fmt) != serialization.load_pem_public_key(PUBLIC_KEY_PEM).public_bytes(**fmt):
        raise ValueError(
            f"{os.path.basename(path) if os.path.exists(path) else 'The built-in key'} does not match the public key inside utils/license_manager.py. "
            "Keys made with it would be rejected by the app. Use the private key that was created together "
            "with that public key."
        )
    return key, path


def make_license_key(private_key, machine_id: str, expiry_date: str) -> str:
    payload = _license_payload(machine_id, expiry_date)
    signature = private_key.sign(
        payload,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256(),
    )
    key_obj = {
        'm': machine_id,
        'e': expiry_date,
        'sig': base64.urlsafe_b64encode(signature).decode().rstrip('='),
    }
    return base64.urlsafe_b64encode(json.dumps(key_obj).encode()).decode().rstrip('=')


class KeygenApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("KRISC License Key Generator - VisionCraft OSMS")
        self.geometry("620x780")
        self.minsize(620, 700)
        self.resizable(True, True)
        self.configure(bg="#f8fafc")

        self.machine_id = None

        self.private_key = None
        self.key_status_var = tk.StringVar()

        pad = {'padx': 16, 'pady': 6}

        tk.Label(self, text="KRISC License Key Generator", font=("Segoe UI", 16, "bold"), bg="#f8fafc").pack(pady=(18, 0))
        tk.Label(self, text="Internal tool -- keep this and the private key file confidential.",
                 font=("Segoe UI", 9), fg="#64748b", bg="#f8fafc").pack(pady=(0, 6))

        # Private-key status is shown at the TOP so it can't be missed.
        key_row = tk.Frame(self, bg="#f8fafc")
        key_row.pack(fill="x", padx=16, pady=(0, 6))
        self.key_status_label = tk.Label(key_row, textvariable=self.key_status_var, font=("Segoe UI", 8),
                                          bg="#f8fafc", wraplength=430, justify="left", anchor="w")
        self.key_status_label.pack(side="left", fill="x", expand=True)
        tk.Button(key_row, text="Browse for private key...", command=self.browse_private_key,
                  bg="#e2e8f0", relief="flat", padx=8, pady=3).pack(side="right")

        # --- System ID input ---
        frame1 = tk.LabelFrame(self, text="1. Paste the customer's System ID", bg="#f8fafc", font=("Segoe UI", 10, "bold"))
        frame1.pack(fill="x", **pad)
        self.system_id_entry = tk.Entry(frame1, font=("Consolas", 12), justify="center")
        self.system_id_entry.pack(fill="x", padx=10, pady=8)
        tk.Button(frame1, text="Parse System ID", command=self.parse_system_id, bg="#2563eb", fg="white",
                  relief="flat", padx=10, pady=4).pack(pady=(0, 8))
        self.parsed_label = tk.Label(frame1, text="Machine ID: --   |   Requested on: --",
                                      font=("Consolas", 10), bg="#f8fafc", fg="#334155")
        self.parsed_label.pack(pady=(0, 8))

        # --- Expiry date ---
        frame2 = tk.LabelFrame(self, text="2. Choose an expiry date", bg="#f8fafc", font=("Segoe UI", 10, "bold"))
        frame2.pack(fill="x", **pad)

        quick_row = tk.Frame(frame2, bg="#f8fafc")
        quick_row.pack(pady=(8, 4))
        for label, days in [("+30 days", 30), ("+90 days", 90), ("+180 days", 180), ("+1 year", 365), ("+2 years", 730)]:
            tk.Button(quick_row, text=label, command=lambda d=days: self.set_expiry_in_days(d),
                      bg="#e2e8f0", relief="flat", padx=8, pady=4).pack(side="left", padx=4)
        tk.Button(quick_row, text="Lifetime", command=self.set_lifetime,
                  bg="#fde68a", relief="flat", padx=8, pady=4).pack(side="left", padx=4)

        date_row = tk.Frame(frame2, bg="#f8fafc")
        date_row.pack(pady=(4, 10))
        tk.Label(date_row, text="Expiry date (YYYY-MM-DD):", bg="#f8fafc").pack(side="left", padx=(10, 6))
        self.expiry_entry = tk.Entry(date_row, font=("Consolas", 12), width=14, justify="center")
        self.expiry_entry.pack(side="left")
        self.set_expiry_in_days(365)

        # --- Generate ---
        tk.Button(self, text="Generate License Key", command=self.generate_key,
                  bg="#16a34a", fg="white", font=("Segoe UI", 11, "bold"), relief="flat",
                  padx=14, pady=8).pack(pady=14)

        frame3 = tk.LabelFrame(self, text="3. Send this key to the customer", bg="#f8fafc", font=("Segoe UI", 10, "bold"))
        frame3.pack(fill="both", expand=True, **pad)
        self.key_text = tk.Text(frame3, height=8, wrap="char", font=("Consolas", 10))
        self.key_text.pack(fill="both", expand=True, padx=10, pady=8)
        self.copy_btn = tk.Button(frame3, text="Copy to Clipboard", command=self.copy_key,
                                   bg="#2563eb", fg="white", relief="flat", padx=10, pady=4)
        self.copy_btn.pack(pady=(0, 8))

        self.refresh_private_key()

    def refresh_private_key(self, path=None):
        try:
            self.private_key, used = load_private_key(path)
            self.key_status_var.set(f"Private key loaded: {used}")
            self.key_status_label.config(fg="#16a34a")
        except Exception as exc:
            self.private_key = None
            self.key_status_var.set(f"PRIVATE KEY PROBLEM: {exc}")
            self.key_status_label.config(fg="#dc2626")

    def browse_private_key(self):
        chosen = filedialog.askopenfilename(
            title="Select krisc_license_private.pem",
            filetypes=[("PEM key files", "*.pem"), ("All files", "*.*")])
        if chosen:
            self.refresh_private_key(chosen)

    def parse_system_id(self):
        sid = self.system_id_entry.get().strip()
        parsed = parse_system_id(sid) if sid else None
        if not parsed:
            self.machine_id = None
            self.parsed_label.config(text="Could not parse that System ID. Check it was pasted in full.", fg="#dc2626")
            return
        machine_id, date_str = parsed
        try:
            requested_on = f"20{date_str[0:2]}-{date_str[2:4]}-{date_str[4:6]}"
        except Exception:
            requested_on = date_str
        self.machine_id = machine_id
        self.parsed_label.config(text=f"Machine ID: {machine_id}   |   Requested on: {requested_on}", fg="#334155")

    def set_expiry_in_days(self, days):
        self.expiry_entry.delete(0, tk.END)
        self.expiry_entry.insert(0, (date.today() + timedelta(days=days)).isoformat())

    def set_lifetime(self):
        self.expiry_entry.delete(0, tk.END)
        self.expiry_entry.insert(0, "2099-12-31")

    def generate_key(self):
        if self.private_key is None:
            messagebox.showerror("Private key missing", "The private key could not be loaded.\n\nSee the red message at the top of the window, or click \"Browse for private key...\" and select krisc_license_private.pem.")
            return
        if not self.machine_id:
            messagebox.showwarning("Parse the System ID first", "Click 'Parse System ID' before generating a key.")
            return
        expiry_date = self.expiry_entry.get().strip()
        try:
            date.fromisoformat(expiry_date)
        except ValueError:
            messagebox.showerror("Invalid date", "Expiry date must be in YYYY-MM-DD format.")
            return

        key = make_license_key(self.private_key, self.machine_id, expiry_date)
        self.key_text.delete("1.0", tk.END)
        self.key_text.insert("1.0", key)
        self.copy_key()  # auto-copy so it's ready to paste into a message right away

    def copy_key(self):
        key = self.key_text.get("1.0", tk.END).strip()
        if not key:
            messagebox.showwarning("Nothing to copy", "Generate a license key first.")
            return
        self.clipboard_clear()
        self.clipboard_append(key)
        self.update()  # ensure the clipboard is flushed to the OS before the window might close

        # Inline feedback instead of a blocking popup.
        original_text, original_bg = self.copy_btn.cget("text"), self.copy_btn.cget("bg")
        self.copy_btn.config(text="Copied!", bg="#16a34a")
        self.after(1200, lambda: self.copy_btn.config(text=original_text, bg=original_bg))


if __name__ == '__main__':
    KeygenApp().mainloop()
