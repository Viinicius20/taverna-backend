from typing import Optional
from fastapi import APIRouter, Depends, UploadFile, File
from pydantic import BaseModel
import time

# AJUSTAR: importe de onde o router de locations já pega essas três coisas
from deps import supabase, usuario_atual, MESTRE

router = APIRouter()


# ---------- descobertas (o mestre revela e esconde) ----------

class DescobertaIn(BaseModel):
    campaign_id: str
    tipo: str
    entidade_id: str
    personagem_id: Optional[str] = None


@router.get("/descobertas")
async def listar_descobertas(campaign_id: str, tipo: Optional[str] = None,
                             user: dict = Depends(usuario_atual)):
    q = supabase.table("descobertas").select("*").eq("campaign_id", campaign_id)
    if tipo:
        q = q.eq("tipo", tipo)
    return {"success": True, "data": q.execute().data}


@router.post("/descobertas", dependencies=MESTRE)
async def revelar(req: DescobertaIn):
    q = (supabase.table("descobertas").select("id")
         .eq("campaign_id", req.campaign_id).eq("tipo", req.tipo)
         .eq("entidade_id", req.entidade_id))
    q = q.eq("personagem_id", req.personagem_id) if req.personagem_id else q.is_("personagem_id", "null")
    if q.execute().data:
        return {"success": True, "ja_existia": True}
    r = supabase.table("descobertas").insert(req.dict()).execute()
    return {"success": True, "data": r.data}


@router.delete("/descobertas/{descoberta_id}", dependencies=MESTRE)
async def esconder(descoberta_id: str):
    supabase.table("descobertas").delete().eq("id", descoberta_id).execute()
    return {"success": True}


# ---------- enciclopédia (a tela dos jogadores) ----------

def _norm_local(r):
    return {"id": r["id"], "nome": r.get("name"),
            "subtitulo": (r.get("type") or "").capitalize(),
            "descricao": r.get("description") or "",
            "imagem": None}


def _norm_monstro(r):
    partes = [r.get("type"), f"CR {r['cr']}" if r.get("cr") else None]
    return {"id": r["id"], "nome": r.get("name"),
            "subtitulo": " · ".join(p for p in partes if p),
            "descricao": "", "imagem": r.get("art_url")}            # AJUSTAR


def _norm_npc(r):
    return {"id": r["id"], "nome": r.get("name"),
            "subtitulo": (r.get("data") or {}).get("race", ""),
            "descricao": "", "imagem": r.get("avatar_url")}


def _norm_item(r):
    oculto = not r.get("identificado")
    partes = [None if oculto else r.get("rarity"), r.get("type")]
    return {"id": r["id"],
            "nome": (r.get("nome_misterioso") or "Item não identificado") if oculto else r.get("name"),
            "subtitulo": " · ".join(p for p in partes if p),
            "descricao": "" if oculto else (r.get("description") or ""),
            "imagem": None if oculto else r.get("art_url")}


TABELAS = {
    "local":   ("locations",   _norm_local,   "locais"),
    "monstro": ("bestiary",    _norm_monstro, "monstros"),
    "npc":     ("characters",  _norm_npc,     "npcs"),
    "item":    ("magic_items", _norm_item,    "itens"),
}


@router.get("/enciclopedia/{campaign_id}")
async def enciclopedia(campaign_id: str, user: dict = Depends(usuario_atual)):
    ids_por_tipo = _ids_descobertos(campaign_id, user)      # ← no lugar de tudo aquilo

    saida = {}
    for tipo, (tabela, norm, chave) in TABELAS.items():
        ids = list(ids_por_tipo.get(tipo, []))
        linhas = supabase.table(tabela).select("*").in_("id", ids).execute().data if ids else []
        saida[chave] = sorted((norm(r) for r in linhas), key=lambda x: (x["nome"] or "").lower())

    return {"success": True, "data": saida}

    saida = {}
    for tipo, (tabela, norm, chave) in TABELAS.items():
        ids = list(ids_por_tipo.get(tipo, []))
        linhas = supabase.table(tabela).select("*").in_("id", ids).execute().data if ids else []
        saida[chave] = sorted((norm(r) for r in linhas), key=lambda x: (x["nome"] or "").lower())

    return {"success": True, "data": saida}

def _ids_descobertos(campaign_id: str, user: dict) -> dict:
    meus = (supabase.table("characters").select("id")
            .eq("campaign_id", campaign_id).eq("user_id", user["sub"]).execute().data)
    meus_ids = {c["id"] for c in meus}
    desc = (supabase.table("descobertas").select("tipo,entidade_id,personagem_id")
            .eq("campaign_id", campaign_id).execute().data)
    por_tipo = {}
    for d in desc:
        if d["personagem_id"] is None or d["personagem_id"] in meus_ids:
            por_tipo.setdefault(d["tipo"], set()).add(str(d["entidade_id"]))
    return por_tipo

def _montar_atlas(campaign_id: str, descobertos=None):
    """descobertos=None: mestre (todos os locais). set: jogador (só os revelados)."""
    mapa = supabase.table("mapas").select("imagem_url").eq("campaign_id", campaign_id).execute().data
    locais = supabase.table("locations").select("*").eq("campaign_id", campaign_id).execute().data
    pins = []
    for r in locais:
        if descobertos is not None and str(r["id"]) not in descobertos:
            continue
        pins.append({**_norm_local(r), "x": r.get("pin_x"), "y": r.get("pin_y")})
    return {"mapa_url": mapa[0]["imagem_url"] if mapa else None, "pins": pins}


@router.get("/atlas/{campaign_id}")
async def atlas(campaign_id: str, user: dict = Depends(usuario_atual)):
    revelados = _ids_descobertos(campaign_id, user).get("local", set())
    return {"success": True, "data": _montar_atlas(campaign_id, revelados)}


@router.get("/atlas-mestre/{campaign_id}", dependencies=MESTRE)
async def atlas_mestre(campaign_id: str):
    return {"success": True, "data": _montar_atlas(campaign_id)}


@router.post("/mapa/{campaign_id}", dependencies=MESTRE)
async def upload_mapa(campaign_id: str, file: UploadFile = File(...)):
    dados, ext = await _ler_imagem(file)      # AJUSTAR: veja a observação abaixo
    nome = f"mapa-{campaign_id}.{ext}"
    supabase.storage.from_("Avatars").upload(
        nome, dados, {"content-type": file.content_type, "upsert": "true"})
    url = f"{_url_publica(nome)}?v={int(time.time())}"
    supabase.table("mapas").upsert({"campaign_id": campaign_id, "imagem_url": url}).execute()
    return {"success": True, "url": url}