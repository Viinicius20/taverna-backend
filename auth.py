import os
import time
import bcrypt
import jwt
from dotenv import load_dotenv
from fastapi import Depends, Header, HTTPException

load_dotenv()

JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    raise RuntimeError("Defina a variável de ambiente JWT_SECRET")

ALGORITMO = "HS256"
DURACAO_SEGUNDOS = 60 * 60 * 24 * 7   # 7 dias


def hash_senha(senha: str) -> str:
    return bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode()


def confere_senha(senha: str, hash_salvo: str) -> bool:
    try:
        return bcrypt.checkpw(senha.encode(), hash_salvo.encode())
    except ValueError:
        return False


def criar_token(perfil: dict) -> str:
    payload = {"sub": perfil["id"], "role": perfil.get("role"), "exp": int(time.time()) + DURACAO_SEGUNDOS}
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITMO)


def usuario_atual(authorization: str = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Não autenticado")
    try:
        return jwt.decode(authorization[7:], JWT_SECRET, algorithms=[ALGORITMO])
    except jwt.PyJWTError:
        raise HTTPException(401, "Sessão inválida ou expirada")


def exigir_mestre(user: dict = Depends(usuario_atual)) -> dict:
    if user.get("role") != "mestre":
        raise HTTPException(403, "Apenas o mestre pode fazer isso")
    return user