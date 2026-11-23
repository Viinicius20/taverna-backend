from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
import re
from typing import Optional
from auth import exigir_mestre
from core import supabase

router = APIRouter()

TABELAS = {"npc": "npcs", "faction": "factions", "location": "locations", "character": "characters"}
COLUNAS = {
    "npc": "id, name, data, relation_score",
    "faction": "id, name, reputation_score",
    "location": "id, name",
    "character": "id, name, data",
}
VINCULOS = {"conhece", "aliado", "rival", "inimigo", "familia", "serve",
            "lidera", "teme", "deve_favor", "vive_em"}

UUID_RE = re.compile(r"^[0-9a-fA-F-]{36}$")


class RelacaoNova(BaseModel):
    source_type: str
    source_id: str
    target_type: str
    target_id: str
    kind: str = "conhece"
    note: str = Field(default="", max_length=300)
    secret: bool = True


def _existe(tipo: str, entidade_id: str) -> bool:
    try:
        res = supabase.table(TABELAS[tipo]).select("id").eq("id", entidade_id).limit(1).execute()
    except Exception:
        return False   # id que não é um uuid válido
    return bool(res.data)


@router.post("/relacoes/{campaign_id}", dependencies=[Depends(exigir_mestre)])
def criar_relacao(campaign_id: str, body: RelacaoNova):
    if body.source_type not in TABELAS or body.target_type not in TABELAS:
        raise HTTPException(400, "Tipo de entidade inválido")
    if body.kind not in VINCULOS:
        raise HTTPException(400, "Tipo de vínculo inválido")
    if (body.source_type, body.source_id) == (body.target_type, body.target_id):
        raise HTTPException(400, "Uma entidade não pode se ligar a ela mesma")
    if not _existe(body.source_type, body.source_id) or not _existe(body.target_type, body.target_id):
        raise HTTPException(400, "Entidade não encontrada")

    repetido = supabase.table("relationships").select("id").eq("campaign_id", campaign_id) \
        .eq("source_type", body.source_type).eq("source_id", body.source_id) \
        .eq("target_type", body.target_type).eq("target_id", body.target_id) \
        .eq("kind", body.kind).limit(1).execute()
    if repetido.data:
        raise HTTPException(409, "Esse vínculo já existe")

    res = supabase.table("relationships").insert({
        "campaign_id": campaign_id,
        "source_type": body.source_type, "source_id": body.source_id,
        "target_type": body.target_type, "target_id": body.target_id,
        "kind": body.kind, "note": body.note.strip(), "secret": body.secret,
    }).execute()
    _sincronizar_conhecidos(res.data[0])
    return {"success": True, "data": res.data[0]}

def filtrar_perspectiva(nos: dict, arestas: list, conhecidos: set, personagem_id: str):
    """O que um jogador veria: personagens e NPCs que ele conhece, sem vínculos secretos."""
    def pode(no):
        if no["tipo"] == "character":
            return True
        return no["tipo"] == "npc" and no["id"].split(":", 1)[1] in conhecidos

    permitidos = {k for k, v in nos.items() if pode(v)}
    visiveis = [a for a in arestas
                if not a["secret"] and a["source"] in permitidos and a["target"] in permitidos]
    usados = {a["source"] for a in visiveis} | {a["target"] for a in visiveis}
    eu = f"character:{personagem_id}"
    if eu in nos:
        usados.add(eu)
    return {k: v for k, v in nos.items() if k in usados}, visiveis

@router.get("/relacoes/{campaign_id}/grafo", dependencies=[Depends(exigir_mestre)])
def grafo(campaign_id: str, como: Optional[str] = None):
    arestas = supabase.table("relationships").select("*").eq("campaign_id", campaign_id).execute().data or []

    ids = {tipo: set() for tipo in TABELAS}
    for a in arestas:
        ids[a["source_type"]].add(a["source_id"])
        ids[a["target_type"]].add(a["target_id"])

    nos = {}
    for tipo, conjunto in ids.items():
        if not conjunto:
            continue
        rows = supabase.table(TABELAS[tipo]).select(COLUNAS[tipo]).in_("id", list(conjunto)).execute().data or []
        for r in rows:
            d = r.get("data") or {}
            nos[f"{tipo}:{r['id']}"] = {
                "id": f"{tipo}:{r['id']}",
                "tipo": tipo,
                "label": d.get("name") or r.get("name") or "(sem nome)",
                "score": r.get("relation_score") if tipo == "npc" else r.get("reputation_score"),
            }

    validas = [
        {"id": a["id"], "source": f"{a['source_type']}:{a['source_id']}",
         "target": f"{a['target_type']}:{a['target_id']}",
         "kind": a["kind"], "note": a["note"], "secret": a["secret"]}
        for a in arestas
        if f"{a['source_type']}:{a['source_id']}" in nos and f"{a['target_type']}:{a['target_id']}" in nos
    ]

    if como:
        if not UUID_RE.match(como):
            raise HTTPException(400, "Personagem inválido")
        conhecidos = {r["npc_id"] for r in (supabase.table("npc_conhecidos").select("npc_id")
                                            .eq("character_id", como).execute().data or [])}
        nos, validas = filtrar_perspectiva(nos, validas, conhecidos, como)
    return {"success": True, "data": {"nos": list(nos.values()), "arestas": validas}}


@router.delete("/relacoes/{campaign_id}/{relacao_id}", dependencies=[Depends(exigir_mestre)])
def apagar_relacao(campaign_id: str, relacao_id: str):
    supabase.table("relationships").delete().eq("id", relacao_id).eq("campaign_id", campaign_id).execute()
    return {"success": True}

class RelacaoEdicao(BaseModel):
    kind: Optional[str] = None
    note: Optional[str] = None
    secret: Optional[bool] = None


def _sincronizar_conhecidos(rel: dict):
    """Vínculo aberto 'conhece' entre personagem e NPC: o personagem passa a conhecer o NPC."""
    if rel.get("kind") != "conhece" or rel.get("secret"):
        return
    if rel["source_type"] == "character" and rel["target_type"] == "npc":
        npc_id, char_id = rel["target_id"], rel["source_id"]
    elif rel["source_type"] == "npc" and rel["target_type"] == "character":
        npc_id, char_id = rel["source_id"], rel["target_id"]
    else:
        return
    try:
        supabase.table("npc_conhecidos").upsert({"npc_id": npc_id, "character_id": char_id}).execute()
    except Exception as e:
        print(f"[AVISO] Não consegui marcar o NPC como conhecido: {e}")


@router.patch("/relacoes/{campaign_id}/{relacao_id}", dependencies=[Depends(exigir_mestre)])
def editar_relacao(campaign_id: str, relacao_id: str, body: RelacaoEdicao):
    if body.kind is not None and body.kind not in VINCULOS:
        raise HTTPException(400, "Tipo de vínculo inválido")
    achado = (supabase.table("relationships").select("*")
              .eq("id", relacao_id).eq("campaign_id", campaign_id).limit(1).execute().data)
    if not achado:
        raise HTTPException(404, "Vínculo não encontrado")
    atual = achado[0]

    campos = {}
    if body.kind is not None:
        campos["kind"] = body.kind
    if body.note is not None:
        campos["note"] = body.note.strip()[:300]
    if body.secret is not None:
        campos["secret"] = body.secret
    if not campos:
        return {"success": True, "data": atual}

    if "kind" in campos:   # não deixa criar um vínculo repetido
        repetido = (supabase.table("relationships").select("id").eq("campaign_id", campaign_id)
                    .eq("source_type", atual["source_type"]).eq("source_id", atual["source_id"])
                    .eq("target_type", atual["target_type"]).eq("target_id", atual["target_id"])
                    .eq("kind", campos["kind"]).neq("id", relacao_id).limit(1).execute().data)
        if repetido:
            raise HTTPException(409, "Esse vínculo já existe")

    supabase.table("relationships").update(campos).eq("id", relacao_id).execute()
    final = {**atual, **campos}
    _sincronizar_conhecidos(final)
    return {"success": True, "data": final}