from cryptography.hazmat.primitives.serialization import load_pem_private_key, Encoding, PrivateFormat, NoEncryption

with open("private_key.pem", "rb") as f:
    priv = load_pem_private_key(f.read(), password=None)

ec_pem = priv.private_bytes(
    Encoding.PEM,
    PrivateFormat.TraditionalOpenSSL,  # gera EC PRIVATE KEY
    NoEncryption()
)

print(ec_pem.decode())

# Versão uma linha pra Render
oneline = ec_pem.decode().replace('\n', '\\n')
print("\nPara o Render:")
print(oneline)

with open("render_key.txt", "w") as f:
    f.write(oneline)
print("Salvo em render_key.txt")