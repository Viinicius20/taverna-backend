import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import exigir_mestre
from core import supabase, campanha_atual

router = APIRouter(tags=["faccao-notas"], dependencies=[Depends(exigir_mestre)])

ID = re.compile(r"^[0-9a-zA-Z-]{1,64}$")
MAX_VALOR, MAX_CAMPO = 5000, 40


class NotasReq(BaseModel):
    notas: dict


def _limpar(notas: dict) -> dict:
    return {c: v[:MAX_VALOR] for c, v in (notas or {}).items()
            if isinstance(c, str) and 1 <= len(c) <= MAX_CAMPO and isinstance(v, str)}


def _campanha(campaign_id: str):
    if campaign_id != campanha_atual():
        raise HTTPException(404, "Campanha não encontrada")


@router.get("/faccao-notas/{campaign_id}")
def listar(campaign_id: str):
    _campanha(campaign_id)
    linhas = (supabase.table("faccao_notas").select("faccao_id, notas")
              .eq("campaign_id", campaign_id).execute().data or [])
    return {"success": True, "data": {l["faccao_id"]: l["notas"] or {} for l in linhas}}


@router.put("/faccao-notas/{campaign_id}/{faccao_id}")
def gravar(campaign_id: str, faccao_id: str, body: NotasReq):
    _campanha(campaign_id)
    if not ID.match(faccao_id):
        raise HTTPException(400, "Facção inválida")
    atual = (supabase.table("faccao_notas").select("notas").eq("campaign_id", campaign_id)
             .eq("faccao_id", faccao_id).limit(1).execute().data)
    novo = {**((atual[0]["notas"] if atual else None) or {}), **_limpar(body.notas)}
    supabase.table("faccao_notas").upsert({
        "campaign_id": campaign_id, "faccao_id": faccao_id, "notas": novo,
        "updated_at": datetime.utcnow().isoformat(),
    }, on_conflict="campaign_id,faccao_id").execute()
    return {"success": True}