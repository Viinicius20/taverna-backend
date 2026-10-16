from getpass import getpass
from core import supabase
from auth import hash_senha

usuario = input("Username: ").strip()
senha = getpass("Nova senha: ")
supabase.table("profiles").update({"password_hash": hash_senha(senha)}).eq("username", usuario).execute()
print("Senha definida.")