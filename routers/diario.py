from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from core import supabase, campanha_atual
from auth import dono_ou_mestre
from fastapi import Depends
from locais_util import indice_de_locais
from routers.enciclopedia import _ja_reveladas, _npcs_por_local

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
               .eq("campaign_id", campanha_atual()).execute().data or [])]
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
        .eq("campaign_id", campanha_atual()).order("created_at", desc=True).execute().data or []
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
        .eq("campaign_id", campanha_atual()).order("session_number", desc=True).execute().data or []
    notas = supabase.table("diario_notas").select("session_number, texto") \
        .eq("character_id", character_id).execute().data or []
    descobertas = (
        supabase.table("diario_descobertas_visiveis")
        .select("tipo,entidade_id,titulo,local_id,dia_total")
        .eq("campaign_id", campanha_atual())
        .order("registrado_em", desc=True)
        .limit(100).execute().data or []
    )

    ids_npcs = {
        str(item["entidade_id"]) for item in descobertas
        if item["tipo"] == "npc"
    }

    if ids_npcs:
        campanha = campanha_atual()
        locais_publicos = {
            entidade_id for tipo, entidade_id in _ja_reveladas(campanha)
            if tipo == "local"
        }
        locais = (
            supabase.table("locations").select("id,name")
            .eq("campaign_id", campanha).execute().data or []
        )
        npcs_por_local = _npcs_por_local(
            campanha, indice_de_locais(locais), ids_npcs, locais_publicos
        )
        pin_por_npc = {
            local_id_npc["id"]: local_id
            for local_id, npcs_do_pin in npcs_por_local.items()
            for local_id_npc in npcs_do_pin
        }

        for item in descobertas:
            if item["tipo"] == "npc":
                item["local_id"] = pin_por_npc.get(item["entidade_id"])

    return {"success": True, "data": {
        "fatos": fatos,
        "npcs": npcs,
        "sessoes": sessoes,
        "notas": notas,
        "descobertas": descobertas,
    }}


@router.put("/diario/{character_id}/nota", dependencies=[Depends(dono_ou_mestre)])
def salvar_nota_diario(character_id: str, body: NotaDiarioReq):
    supabase.table("diario_notas").upsert({
        "character_id": character_id,
        "session_number": body.session_number,
        "texto": body.texto[:5000],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }, on_conflict="character_id,session_number").execute()
    return {"ok": True}