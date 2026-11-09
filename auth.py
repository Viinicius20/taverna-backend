import os
import time
import bcrypt
import jwt
from dotenv import load_dotenv
from fastapi import Depends, Header, HTTPException, Request
from core import supabase


load_dotenv()

JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    raise RuntimeError("Defina a variável de ambiente JWT_SECRET")

ALGORITMO = "HS256"
DURACAO_SEGUNDOS = 60 * 60 * 24 * 7
_cache_membro: dict = {}
_ABERTAS = ("/profiles", "/campaigns/join", "/campaigns/by-owner", "/docs", "/openapi.json", "/redoc")


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

MESTRE = [Depends(exigir_mestre)]

def usuario_opcional(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        return jwt.decode(authorization[7:], JWT_SECRET, algorithms=[ALGORITMO])
    except jwt.PyJWTError:
        return None

def dono_ou_mestre(character_id: str, user: dict = Depends(usuario_atual)) -> dict:
    """Mestre passa sempre. Jogador só mexe no personagem que é dele."""
    if user.get("role") == "mestre":
        return user
    r = supabase.table("characters").select("user_id").eq("id", character_id).limit(1).execute().data
    if not r or r[0].get("user_id") != user.get("sub"):
        raise HTTPException(403, "Este personagem não é seu")
    return user

def checar_campanha(request: Request, authorization: str = Header(None)):
    if request.method == "OPTIONS" or request.url.path.startswith(_ABERTAS) or request.url.path == "/":
        return
    user = usuario_opcional(authorization)
    if not user:
        return  # as rotas protegidas devolvem 401 sozinhas
    from core import campanha_atual
    camp, uid = campanha_atual(), user["sub"]
    chave = (uid, camp)
    agora = time.time()
    if _cache_membro.get(chave, 0) > agora:
        return
    try:
        membro = supabase.table("campaign_members").select("user_id").eq("campaign_id", camp).eq("user_id", uid).limit(
            1).execute().data
        dono = supabase.table("campaigns").select("id").eq("id", camp).eq("owner_id", uid).limit(1).execute().data
    except Exception:
        raise HTTPException(503, "Não foi possível validar a campanha agora")
    if not (membro or dono):
        raise HTTPException(403, "Você não faz parte desta campanha")
    _cache_membro[chave] = agora + 60


def dono_da_lista(owner_id: str, user: dict = Depends(usuario_atual)) -> dict:
    if user["sub"] != owner_id:
        raise HTTPException(403, "Acesso negado")
    return user
