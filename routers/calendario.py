from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from auth import exigir_mestre
from core import supabase, CAMPANHA_ID
from servicos import calendario_atual, gravar_calendario, avancar_calendario
from utils import para_dia_total
from datetime import datetime
from utils import para_dia_total, MESES_PADRAO


def campanha_valida(campaign_id: str):
    if campaign_id != CAMPANHA_ID:
        raise HTTPException(404, "Campanha não encontrada")


router = APIRouter(tags=["calendario"], dependencies=[Depends(campanha_valida)])


class AvancarReq(BaseModel):
    dias: int = Field(ge=1, le=365)
    motivo: str = Field(default="", max_length=120)


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
        "ano_inicial": cal["ano_inicial"],
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

class ResetReq(BaseModel):
    ano: int = Field(default=1, ge=0, le=99999)
    meses_padrao: bool = False
    limpar_historico: bool = True


@router.delete("/calendario/{campaign_id}/historico/{log_id}", dependencies=[Depends(exigir_mestre)])
def apagar_linha(campaign_id: str, log_id: str):
    supabase.table("calendario_log").delete().eq("id", log_id).eq("campaign_id", campaign_id).execute()
    return {"success": True}


@router.delete("/calendario/{campaign_id}/historico", dependencies=[Depends(exigir_mestre)])
def limpar_historico(campaign_id: str):
    supabase.table("calendario_log").delete().eq("campaign_id", campaign_id).execute()
    return {"success": True}


@router.post("/calendario/{campaign_id}/resetar", dependencies=[Depends(exigir_mestre)])
def resetar(campaign_id: str, body: ResetReq):
    antes = calendario_atual(campaign_id)          # garante que a linha existe
    campos = {"dia_total": 0, "ano_inicial": body.ano, "updated_at": datetime.utcnow().isoformat()}
    if body.meses_padrao:
        campos["meses"] = MESES_PADRAO
    supabase.table("calendario").update(campos).eq("campaign_id", campaign_id).execute()

    # os prazos dos eventos usavam a contagem antiga de dias, então saem
    supabase.table("world_events").update({"data_alvo": None, "prazo_avisado": False}) \
        .eq("campaign_id", campaign_id).execute()

    if body.limpar_historico:
        supabase.table("calendario_log").delete().eq("campaign_id", campaign_id).execute()

    depois = calendario_atual(campaign_id)
    if not body.limpar_historico:
        supabase.table("calendario_log").insert({
            "campaign_id": campaign_id, "dias": 0, "motivo": "Calendário reiniciado",
            "data_antes": antes["texto"], "data_depois": depois["texto"],
        }).execute()
    return {"success": True, "data": {"data": depois["data"], "texto": depois["texto"], "meses": depois["meses"]}}

NAO_REVERSIVEIS = {"Meses reconfigurados", "Calendário reiniciado"}


class VoltarReq(BaseModel):
    log_id: str


def _delta(linha: dict):
    if linha.get("motivo") in NAO_REVERSIVEIS:
        return None
    if linha.get("dia_antes") is not None and linha.get("dia_depois") is not None:
        return linha["dia_depois"] - linha["dia_antes"]
    if (linha.get("dias") or 0) > 0:
        return linha["dias"]
    return None


@router.post("/calendario/{campaign_id}/voltar", dependencies=[Depends(exigir_mestre)])
def voltar(campaign_id: str, body: VoltarReq):
    alvo = supabase.table("calendario_log").select("*") \
        .eq("id", body.log_id).eq("campaign_id", campaign_id).limit(1).execute().data
    if not alvo:
        raise HTTPException(404, "Linha não encontrada")

    # esta linha e todas as mais novas
    linhas = supabase.table("calendario_log").select("*").eq("campaign_id", campaign_id) \
        .gte("created_at", alvo[0]["created_at"]).execute().data or []

    total = 0
    for l in linhas:
        d = _delta(l)
        if d is None:
            raise HTTPException(400, "Há um ajuste de meses ou um reinício no caminho. Use Definir data.")
        total += d

    cal = calendario_atual(campaign_id)
    novo = max(0, cal["dia_total"] - total)
    supabase.table("calendario").update({"dia_total": novo, "updated_at": datetime.utcnow().isoformat()}) \
        .eq("campaign_id", campaign_id).execute()
    supabase.table("calendario_log").delete().in_("id", [l["id"] for l in linhas]).execute()

    supabase.table("world_events").update({"prazo_avisado": False}) \
        .eq("campaign_id", campaign_id).gt("data_alvo", novo).execute()

    depois = calendario_atual(campaign_id)
    return {"success": True, "data": {"data": depois["data"], "texto": depois["texto"]}}