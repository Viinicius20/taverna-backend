from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import exigir_mestre
from core import supabase, campanha_atual

router = APIRouter(tags=["lendas"], dependencies=[Depends(exigir_mestre)])

DIAS_POR_VOLTA = 7


class LendaIn(BaseModel):
    titulo: str
    verdade: str = ""
    versao_popular: str = ""
    ativa: bool = True


class LendaUpdate(BaseModel):
    titulo: Optional[str] = None
    verdade: Optional[str] = None
    versao_popular: Optional[str] = None
    ativa: Optional[bool] = None
    distorcao: Optional[int] = None
    ultimo_boato: Optional[str] = None


@router.get("/lendas")
def listar():
    r = (supabase.table("lendas").select("*")
         .eq("campaign_id", campanha_atual()).order("criado_em").execute())
    return {"success": True, "data": r.data}


@router.post("/lendas")
def criar(req: LendaIn):
    if not req.titulo.strip():
        raise HTTPException(400, "Dê um título à lenda.")
    r = supabase.table("lendas").insert({
        "campaign_id": campanha_atual(),
        "titulo": req.titulo.strip()[:120],
        "verdade": req.verdade[:3000],
        "versao_popular": req.versao_popular[:3000],
        "ativa": req.ativa,
    }).execute()
    return {"success": True, "data": r.data[0]}


@router.patch("/lendas/{lenda_id}")
def atualizar(lenda_id: str, req: LendaUpdate):
    campos = {k: v for k, v in req.dict().items() if v is not None}
    for k in ("verdade", "versao_popular", "ultimo_boato"):
        if k in campos:
            campos[k] = campos[k][:3000]
    if "titulo" in campos:
        campos["titulo"] = campos["titulo"].strip()[:120]
        if not campos["titulo"]:
            del campos["titulo"]
    if campos:
        (supabase.table("lendas").update(campos)
         .eq("id", lenda_id).eq("campaign_id", campanha_atual()).execute())
    return {"success": True}


@router.delete("/lendas/{lenda_id}")
def apagar(lenda_id: str):
    (supabase.table("lendas").delete()
     .eq("id", lenda_id).eq("campaign_id", campanha_atual()).execute())
    return {"success": True}

def distorcer_com_o_tempo(campaign_id: str, dias: int):
    """A cada DIAS_POR_VOLTA dias, a fofoca em circulação dá mais uma volta; passando de 6, recomeça."""
    voltas = int(dias or 0) // DIAS_POR_VOLTA
    if voltas <= 0:
        return
    lendas = (supabase.table("lendas").select("id, distorcao, ultimo_boato")
              .eq("campaign_id", campaign_id).eq("ativa", True).execute().data or [])
    for l in lendas:
        if not (l.get("ultimo_boato") or "").strip():
            continue                      # sem fofoca circulando, nada a distorcer
        n = (l.get("distorcao") or 0) + voltas
        campos = {"ultimo_boato": "", "distorcao": 0} if n >= 6 else {"distorcao": n}
        supabase.table("lendas").update(campos).eq("id", l["id"]).execute()