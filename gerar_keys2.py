from py_vapid import Vapid
import base64

vapid = Vapid()
vapid.generate_keys()
vapid.save_key("private_key.pem")
vapid.save_public_key("public_key.pem")

# Converte public key PEM pra base64 URL-safe
from cryptography.hazmat.primitives.serialization import load_pem_public_key, Encoding, PublicFormat

with open("public_key.pem", "rb") as f:
    pub = load_pem_public_key(f.read())

pub_bytes = pub.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
pub_b64 = base64.urlsafe_b64encode(pub_bytes).decode().rstrip('=')
print("PUBLIC BASE64:", pub_b64)

# Converte private key PEM pra base64 URL-safe
from cryptography.hazmat.primitives.serialization import load_pem_private_key, Encoding, PrivateFormat, NoEncryption

with open("private_key.pem", "rb") as f:
    priv = load_pem_private_key(f.read(), password=None)

priv_bytes = priv.private_bytes(Encoding.PEM, PrivateFormat.TraditionalOpenSSL, NoEncryption())
priv_b64 = base64.urlsafe_b64encode(priv_bytes).decode().rstrip('=')
print("PRIVATE BASE64:", priv_b64)