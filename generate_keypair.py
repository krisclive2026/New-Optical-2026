"""
Run this ONCE to create the KRISC license signing keypair.

Produces:
  krisc_license_private.pem  -- keep this secret, only used by keygen_tool.py
  krisc_license_public.pem   -- paste its contents into
                                 utils/license_manager.py (PUBLIC_KEY_PEM)

If krisc_license_private.pem already exists, this script refuses to
overwrite it (regenerating would invalidate every key you've already
issued to customers).
"""
import os
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

PRIVATE_PATH = "krisc_license_private.pem"
PUBLIC_PATH = "krisc_license_public.pem"

if os.path.exists(PRIVATE_PATH):
    raise SystemExit(
        f"{PRIVATE_PATH} already exists -- refusing to overwrite it.\n"
        "Delete it manually first ONLY if you understand this will invalidate "
        "every license key you have already issued."
    )

private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
public_key = private_key.public_key()

priv_pem = private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
)
pub_pem = public_key.public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
)

with open(PRIVATE_PATH, "wb") as f:
    f.write(priv_pem)
with open(PUBLIC_PATH, "wb") as f:
    f.write(pub_pem)

print(f"Wrote {PRIVATE_PATH} (keep secret, never ship to customers)")
print(f"Wrote {PUBLIC_PATH} -- paste this into utils/license_manager.py:\n")
print(pub_pem.decode())
