from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from core import supabase, CAMPANHA_ID
from auth import dono_ou_mestre
from fastapi import Depends

from auth import dono_ou_mestre, exigir_mestre

router = APIRouter(tags=["diario"])


class ApresentarNpcReq(BaseModel):
    todos: bool = False
    character_ids: list[str] = []


class NotaDiarioReq(BaseModel):
    session_number: int
    texto: str


@router.post("/npcs/{npc_id}/apresentar", dependencies=[Depends(exigir_mestre)])
def apresentar_npc(npc_id: str, body: ApresentarNpcReq):
    n = supabase.table("npcs").select("id").eq("id", npc_id).limit(1).execute().data
    if not n:
        raise HTTPException(404, "NPC não encontrado")
    if body.todos:
        ids = [c["id"] for c in (supabase.table("characters").select("id")
               .eq("campaign_id", CAMPANHA_ID).execute().data or [])]
    else:
        ids = list(dict.fromkeys(body.character_ids))[:50]
    if not ids:
        raise HTTPException(400, "Escolha ao menos um destinatário")
    supabase.table("npc_conhecidos").upsert(
        [{"npc_id": npc_id, "character_id": cid} for cid in ids]
    ).execute()
    return {"success": True, "enviados": len(ids)}


@router.get("/diario/{character_id}", dependencies=[Depends(dono_ou_mestre)])
def diario_do_personagem(character_id: str):
    fatos_raw = supabase.table("fatos_mundo").select("*") \
        .eq("campaign_id", CAMPANHA_ID).order("created_at", desc=True).execute().data or []
    fatos = [
        {"id": f["id"], "texto": f["texto"]}
        for f in fatos_raw
        if f.get("todos_jogadores") or character_id in (f.get("personagens_que_sabem") or [])
    ]

    rec = supabase.table("npc_conhecidos").select("npc_id").eq("character_id", character_id).execute().data or []
    npc_ids = [r["npc_id"] for r in rec]
    npcs = []
    if npc_ids:
        for n in supabase.table("npcs").select("id, name, data").in_("id", npc_ids).execute().data or []:
            d = n.get("data") or {}
            npcs.append({
                "id": n["id"],
                "name": n["name"],
                "art_url": d.get("art_url"),
                "race": d.get("race"),
                "occupation": d.get("occupation") or d.get("role"),
            })

    sessoes = supabase.table("sessions").select("session_number, title") \
        .eq("campaign_id", CAMPANHA_ID).order("session_number", desc=True).execute().data or []
    notas = supabase.table("diario_notas").select("session_number, texto") \
        .eq("character_id", character_id).execute().data or []

    return {"success": True, "data": {"fatos": fatos, "npcs": npcs, "sessoes": sessoes, "notas": notas}}


@router.put("/diario/{character_id}/nota", dependencies=[Depends(dono_ou_mestre)])
def salvar_nota_diario(character_id: str, body: NotaDiarioReq):
    supabase.table("diario_notas").upsert({
        "character_id": character_id,
        "session_number": body.session_number,
        "texto": body.texto[:5000],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }, on_conflict="character_id,session_number").execute()
    return {"ok": True}