from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import exigir_mestre
from core import supabase, campanha_atual

router = APIRouter(tags=["faccoes-atlas"], dependencies=[Depends(exigir_mestre)])

LIBERA = {"neutra", "aliada"}


class PresencaIn(BaseModel):
    faccao_id: str
    regiao_id: str


class SegredoIn(BaseModel):
    faccao_id: str
    texto: str
    libera_em: str = "aliada"


@router.post("/faccoes-atlas/presenca")
def adicionar_presenca(req: PresencaIn):
    supabase.table("faccao_presenca").upsert(
        {"campaign_id": campanha_atual(), "faccao_id": req.faccao_id, "regiao_id": req.regiao_id},
        on_conflict="faccao_id,regiao_id").execute()
    return {"success": True}


@router.delete("/faccoes-atlas/presenca/{regiao_id}/{faccao_id}")
def remover_presenca(regiao_id: str, faccao_id: str):
    (supabase.table("faccao_presenca").delete()
     .eq("campaign_id", campanha_atual()).eq("regiao_id", regiao_id).eq("faccao_id", faccao_id).execute())
    return {"success": True}


@router.get("/faccao-segredos/{faccao_id}")
def listar_segredos(faccao_id: str):
    r = (supabase.table("faccao_segredos").select("*")
         .eq("campaign_id", campanha_atual()).eq("faccao_id", faccao_id).order("criado_em").execute())
    return {"success": True, "data": r.data}


@router.post("/faccao-segredos")
def criar_segredo(req: SegredoIn):
    texto = req.texto.strip()
    if not texto:
        raise HTTPException(400, "Escreva o segredo.")
    if req.libera_em not in LIBERA:
        raise HTTPException(400, "Patamar inválido.")
    r = supabase.table("faccao_segredos").insert({
        "campaign_id": campanha_atual(), "faccao_id": req.faccao_id,
        "texto": texto[:2000], "libera_em": req.libera_em,
    }).execute()
    return {"success": True, "data": r.data[0]}


@router.delete("/faccao-segredos/{segredo_id}")
def apagar_segredo(segredo_id: str):
    (supabase.table("faccao_segredos").delete()
     .eq("id", segredo_id).eq("campaign_id", campanha_atual()).execute())
    return {"success": True}