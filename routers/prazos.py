from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from auth import exigir_mestre
from core import supabase
from servicos import calendario_atual

router = APIRouter(tags=["prazos"])


class PrazoReq(BaseModel):
    remover: bool = False
    em_dias: Optional[int] = Field(default=None, ge=1, le=36500)


@router.put("/world-events/{event_id}/prazo", dependencies=[Depends(exigir_mestre)])
def definir_prazo(event_id: str, body: PrazoReq):
    ev = supabase.table("world_events").select("id, campaign_id").eq("id", event_id).limit(1).execute().data
    if not ev:
        raise HTTPException(404, "Evento não encontrado")

    if body.remover:
        supabase.table("world_events").update({"data_alvo": None, "prazo_avisado": False}).eq("id", event_id).execute()
        return {"success": True, "data_alvo": None}

    if body.em_dias is None:
        raise HTTPException(400, "Informe em quantos dias")
    cal = calendario_atual(ev[0]["campaign_id"])
    alvo = cal["dia_total"] + body.em_dias
    supabase.table("world_events").update({"data_alvo": alvo, "prazo_avisado": False}).eq("id", event_id).execute()
    return {"success": True, "data_alvo": alvo}