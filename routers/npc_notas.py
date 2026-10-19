import re
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from auth import exigir_mestre
from core import supabase, CAMPANHA_ID

router = APIRouter(tags=["npc-notas"], dependencies=[Depends(exigir_mestre)])

UUID = re.compile(r"^[0-9a-fA-F-]{36}$")
MAX_VALOR, MAX_CAMPO = 5000, 40


class NotasReq(BaseModel):
    notas: dict


def separar_chave(chave):
    """'<uuid>_objetivo_atual' -> ('<uuid>', 'objetivo_atual'); o uuid não tem '_'."""
    if not isinstance(chave, str) or "_" not in chave:
        return None
    npc_id, campo = chave.split("_", 1)
    if UUID.match(npc_id) and 1 <= len(campo) <= MAX_CAMPO:
        return npc_id, campo
    return None


def _limpar(notas: dict) -> dict:
    return {c: v[:MAX_VALOR] for c, v in (notas or {}).items()
            if isinstance(c, str) and 1 <= len(c) <= MAX_CAMPO and isinstance(v, str)}


def _campanha(campaign_id: str):
    if campaign_id != CAMPANHA_ID:
        raise HTTPException(404, "Campanha não encontrada")


def _todas(campaign_id: str) -> dict:
    linhas = supabase.table("npc_notas").select("npc_id, notas").eq("campaign_id", campaign_id).execute().data or []
    return {l["npc_id"]: l["notas"] or {} for l in linhas}


@router.get("/npc-notas/{campaign_id}")
def listar(campaign_id: str):
    _campanha(campaign_id)
    return {"success": True, "data": _todas(campaign_id)}


@router.put("/npc-notas/{campaign_id}/{npc_id}")
def gravar(campaign_id: str, npc_id: str, body: NotasReq):
    _campanha(campaign_id)
    if not UUID.match(npc_id):
        raise HTTPException(400, "NPC inválido")
    atual = supabase.table("npc_notas").select("notas").eq("campaign_id", campaign_id) \
        .eq("npc_id", npc_id).limit(1).execute().data
    novo = {**((atual[0]["notas"] if atual else None) or {}), **_limpar(body.notas)}
    supabase.table("npc_notas").upsert({
        "campaign_id": campaign_id, "npc_id": npc_id, "notas": novo,
        "updated_at": datetime.utcnow().isoformat(),
    }, on_conflict="campaign_id,npc_id").execute()
    return {"success": True}


@router.post("/npc-notas/{campaign_id}/migrar")
def migrar(campaign_id: str, body: NotasReq):
    """Sobe as notas do navegador ({'<npc>_<campo>': texto}). O que já está no servidor vence."""
    _campanha(campaign_id)
    por_npc = {}
    for chave, valor in body.notas.items():
        par = separar_chave(chave)
        if par and isinstance(valor, str) and valor.strip():
            por_npc.setdefault(par[0], {})[par[1]] = valor
    if len(por_npc) > 500:
        raise HTTPException(400, "Notas demais para migrar")

    existentes = _todas(campaign_id)
    linhas = []
    for npc_id, locais in por_npc.items():
        junto = {**_limpar(locais), **(existentes.get(npc_id) or {})}
        if junto != existentes.get(npc_id):
            linhas.append({"campaign_id": campaign_id, "npc_id": npc_id, "notas": junto,
                           "updated_at": datetime.utcnow().isoformat()})
    if linhas:
        supabase.table("npc_notas").upsert(linhas, on_conflict="campaign_id,npc_id").execute()
    return {"success": True, "migrados": len(linhas), "data": _todas(campaign_id)}