from py_vapid import Vapid

vapid = Vapid()
vapid.generate_keys()
vapid.save_key("private_key.pem")

# Usa o método nativo do py_vapid pra exportar no formato correto
print("PUBLIC:", vapid.public_key.public_bytes(
    encoding=__import__('cryptography.hazmat.primitives.serialization', fromlist=['Encoding']).Encoding.X962,
    format=__import__('cryptography.hazmat.primitives.serialization', fromlist=['PublicFormat']).PublicFormat.UncompressedPoint
).hex())

# Salva o PEM da private key diretamente — o pywebpush aceita PEM
print("\nPRIVATE PEM (copie tudo incluindo as linhas BEGIN/END):")
with open("private_key.pem") as f:
    print(f.read())