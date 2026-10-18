from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from auth import exigir_mestre
from core import supabase, CAMPANHA_ID
from servicos import calendario_atual, gravar_calendario, avancar_calendario
from utils import para_dia_total


def campanha_valida(campaign_id: str):
    if campaign_id != CAMPANHA_ID:
        raise HTTPException(404, "Campanha não encontrada")


router = APIRouter(tags=["calendario"], dependencies=[Depends(campanha_valida)])


class AvancarReq(BaseModel):
    dias: int = Field(ge=1, le=3650)
    motivo: Optional[str] = Field(default=None, max_length=200)


class DataReq(BaseModel):
    ano: int
    mes: int
    dia: int


class MesesReq(BaseModel):
    meses: list[dict]


@router.get("/calendario/{campaign_id}")
def ver_calendario(campaign_id: str):
    cal = calendario_atual(campaign_id)
    return {"success": True, "data": {
        "data": cal["data"], "texto": cal["texto"], "meses": cal["meses"], "dia_total": cal["dia_total"],
    }}


@router.post("/calendario/{campaign_id}/avancar", dependencies=[Depends(exigir_mestre)])
def avancar(campaign_id: str, body: AvancarReq):
    cal = avancar_calendario(campaign_id, body.dias, body.motivo)
    return {"success": True, "data": {"data": cal["data"], "texto": cal["texto"]}}


@router.put("/calendario/{campaign_id}/data", dependencies=[Depends(exigir_mestre)])
def definir_data(campaign_id: str, body: DataReq):
    cal = calendario_atual(campaign_id)
    meses = cal["meses"]
    if not 1 <= body.mes <= len(meses):
        raise HTTPException(400, "Mês inválido")
    if not 1 <= body.dia <= meses[body.mes - 1]["dias"]:
        raise HTTPException(400, f"Esse mês tem {meses[body.mes - 1]['dias']} dias")
    novo = para_dia_total(body.ano, body.mes, body.dia, meses, cal["ano_inicial"])
    if novo < 0:
        raise HTTPException(400, f"O calendário começa no ano {cal['ano_inicial']}")
    depois = gravar_calendario(campaign_id, {"dia_total": novo}, 0, "Data definida pelo mestre", cal)
    return {"success": True, "data": {"data": depois["data"], "texto": depois["texto"]}}


@router.put("/calendario/{campaign_id}/meses", dependencies=[Depends(exigir_mestre)])
def definir_meses(campaign_id: str, body: MesesReq):
    novos = []
    for m in body.meses:
        nome = str(m.get("nome", "")).strip()[:30]
        try:
            dias = int(m.get("dias", 0))
        except (TypeError, ValueError):
            dias = 0
        if not nome or not 1 <= dias <= 60:
            raise HTTPException(400, "Cada mês precisa de nome e de 1 a 60 dias")
        novos.append({"nome": nome, "dias": dias})
    if not 1 <= len(novos) <= 24:
        raise HTTPException(400, "Use de 1 a 24 meses")

    cal = calendario_atual(campaign_id)
    d = cal["data"]                      # mantém a data de hoje no calendário novo
    mes = min(d["mes"], len(novos))
    dia = min(d["dia"], novos[mes - 1]["dias"])
    novo_dia = max(0, para_dia_total(d["ano"], mes, dia, novos, cal["ano_inicial"]))
    depois = gravar_calendario(campaign_id, {"meses": novos, "dia_total": novo_dia}, 0, "Meses reconfigurados", cal)
    return {"success": True, "data": {"data": depois["data"], "texto": depois["texto"], "meses": depois["meses"]}}


@router.get("/calendario/{campaign_id}/historico", dependencies=[Depends(exigir_mestre)])
def historico(campaign_id: str):
    r = supabase.table("calendario_log").select("*").eq("campaign_id", campaign_id) \
        .order("created_at", desc=True).limit(20).execute()
    return {"data": r.data}