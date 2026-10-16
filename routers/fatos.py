from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from core import supabase

router = APIRouter(tags=["fatos"])


class FatoCriarReq(BaseModel):
    campaign_id: str
    texto: str
    todos_jogadores: bool = False
    personagens_que_sabem: list[str] = []
    npcs_que_sabem: list[str] = []


class FatoEditarReq(BaseModel):
    texto: Optional[str] = None
    todos_jogadores: Optional[bool] = None
    personagens_que_sabem: Optional[list[str]] = None
    npcs_que_sabem: Optional[list[str]] = None


@router.post("/fatos-mundo")
def criar_fato(req: FatoCriarReq):
    r = supabase.table("fatos_mundo").insert(req.dict()).execute()
    return {"data": r.data[0]}


@router.get("/fatos-mundo/{campaign_id}")
def listar_fatos(campaign_id: str):
    r = supabase.table("fatos_mundo").select("*").eq("campaign_id", campaign_id) \
        .order("created_at", desc=True).execute()
    return {"data": r.data}


@router.patch("/fatos-mundo/{fato_id}")
def editar_fato(fato_id: str, req: FatoEditarReq):
    campos = {k: v for k, v in req.dict().items() if v is not None}
    if not campos:
        raise HTTPException(400, "Nada pra atualizar")
    r = supabase.table("fatos_mundo").update(campos).eq("id", fato_id).execute()
    return {"data": r.data[0] if r.data else None}


@router.delete("/fatos-mundo/{fato_id}")
def deletar_fato(fato_id: str):
    supabase.table("fatos_mundo").delete().eq("id", fato_id).execute()
    return {"ok": True}