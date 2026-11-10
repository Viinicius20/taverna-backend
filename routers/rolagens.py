from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from auth import exigir_mestre, usuario_atual
from core import supabase, campanha_atual, limiter
from motor_dados import ExpressaoInvalida, rolar

router = APIRouter(prefix="/rolagens", tags=["rolagens"])


class RolagemReq(BaseModel):
    expressao: str
    rotulo: Optional[str] = None
    character_id: Optional[str] = None
    oculta: bool = False
    modo: Literal["normal", "vantagem", "desvantagem"] = "normal"


def _nome(user_id: str) -> str:
    r = supabase.table("profiles").select("username").eq("id", user_id).limit(1).execute().data
    return r[0]["username"] if r else "?"


@router.post("")
@limiter.limit("60/minute")
def criar_rolagem(request: Request, req: RolagemReq, user: dict = Depends(usuario_atual)):
    try:
        resultado = rolar(req.expressao, req.modo)
    except ExpressaoInvalida as e:
        raise HTTPException(400, str(e))

    mestre = user.get("role") == "mestre"
    if req.character_id and not mestre:
        dono = supabase.table("characters").select("user_id").eq("id", req.character_id).limit(1).execute().data
        if not dono or dono[0].get("user_id") != user["sub"]:
            raise HTTPException(403, "Este personagem não é seu")

    try:
        linha = supabase.table("rolagens").insert({
            "campaign_id": campanha_atual(),
            "user_id": user["sub"],
            "character_id": req.character_id,
            "autor": _nome(user["sub"]),
            "rotulo": (req.rotulo or "")[:60] or None,
            "expressao": resultado["expressao"],
            "dados": resultado["dados"],
            "modificador": resultado["modificador"],
            "total": resultado["total"],
            "oculta": req.oculta and mestre,   # só o mestre rola escondido
        }).execute().data[0]
    except Exception as e:
        print(f"ERRO ROLAGEM: {e}")
        raise HTTPException(500, "Erro ao registrar rolagem")
    return {"success": True, "data": linha}


@router.get("")
def listar_rolagens(depois: str = "", limite: int = 50, user: dict = Depends(usuario_atual)):
    limite = max(1, min(limite, 100))
    if depois:
        try:
            datetime.fromisoformat(depois.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(400, "Parâmetro 'depois' inválido")
    try:
        q = supabase.table("rolagens").select("*").eq("campaign_id", campanha_atual())
        if user.get("role") != "mestre":
            q = q.eq("oculta", False)
        if depois:
            q = q.gt("created_at", depois)
        linhas = q.order("created_at", desc=True).limit(limite).execute().data or []
    except Exception as e:
        print(f"ERRO LISTAR ROLAGENS: {e}")
        raise HTTPException(500, "Erro ao buscar rolagens")
    return {"success": True, "data": linhas}

@router.delete("", dependencies=[Depends(exigir_mestre)])
def limpar_rolagens():
    try:
        supabase.table("rolagens").delete().eq("campaign_id", campanha_atual()).execute()
    except Exception as e:
        print(f"ERRO LIMPAR ROLAGENS: {e}")
        raise HTTPException(500, "Erro ao limpar rolagens")
    return {"success": True}