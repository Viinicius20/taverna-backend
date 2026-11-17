from typing import Optional
from fastapi import APIRouter, Depends, UploadFile, File
from pydantic import BaseModel
import time
import json

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

def _montar_atlas(campaign_id: str, locais_ok=None, regioes_ok=None):
    """None = mestre (tudo). set = jogador (só o que foi revelado)."""
    mapa = supabase.table("mapas").select("imagem_url").eq("campaign_id", campaign_id).execute().data
    locais = supabase.table("locations").select("*").eq("campaign_id", campaign_id).execute().data
    regioes = supabase.table("regioes").select("*").eq("campaign_id", campaign_id).execute().data

    pins = [
        {**_norm_local(r), "x": r.get("pin_x"), "y": r.get("pin_y"), "regiao_id": r.get("regiao_id")}
        for r in locais
        if locais_ok is None or str(r["id"]) in locais_ok
    ]
    regs = [
        {"id": g["id"], "nome": g["nome"], "descricao": g.get("descricao") or "", "pontos": g.get("pontos") or []}
        for g in regioes
        if regioes_ok is None or str(g["id"]) in regioes_ok
    ]
    return {"mapa_url": mapa[0]["imagem_url"] if mapa else None, "pins": pins, "regioes": regs}


@router.get("/atlas/{campaign_id}")
async def atlas(campaign_id: str, user: dict = Depends(usuario_atual)):
    rev = _ids_descobertos(campaign_id, user)
    return {"success": True, "data": _montar_atlas(campaign_id, rev.get("local", set()), rev.get("regiao", set()))}


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

class RegiaoIn(BaseModel):
    campaign_id: str
    nome: str
    descricao: str = ""
    pontos: list = []


class RegiaoUpdate(BaseModel):
    nome: Optional[str] = None
    descricao: Optional[str] = None
    pontos: Optional[list] = None


@router.post("/regioes", dependencies=MESTRE)
async def criar_regiao(req: RegiaoIn):
    r = supabase.table("regioes").insert(req.dict()).execute()
    return {"success": True, "data": r.data[0]}


@router.patch("/regioes/{regiao_id}", dependencies=MESTRE)
async def atualizar_regiao(regiao_id: str, req: RegiaoUpdate):
    updates = {k: v for k, v in req.dict().items() if v is not None}
    if updates:
        supabase.table("regioes").update(updates).eq("id", regiao_id).execute()
    return {"success": True}


@router.delete("/regioes/{regiao_id}", dependencies=MESTRE)
async def deletar_regiao(regiao_id: str):
    supabase.table("locations").update({"regiao_id": None}).eq("regiao_id", regiao_id).execute()
    supabase.table("regioes").delete().eq("id", regiao_id).execute()
    return {"success": True}

class GerarRegiaoIn(BaseModel):
    contexto: str = ""

@router.post("/regioes/{regiao_id}/gerar", dependencies=MESTRE)
async def gerar_regiao(regiao_id: str, req: GerarRegiaoIn):
    g = supabase.table("regioes").select("*").eq("id", regiao_id).execute().data[0]
    prompt = (
        f"Você ajuda um mestre de RPG a criar uma região de fantasia chamada '{g['nome']}'. "
        f"Contexto do mestre: {req.contexto or 'nenhum'}. "
        'Responda SOMENTE com JSON: {"descricao": "2 a 3 parágrafos sobre clima, cultura e perigos", '
        '"cidades": [{"nome": "...", "descricao": "1 parágrafo"}]} com 2 a 4 cidades. '
        "Em português do Brasil."
    )
    texto = await chamar_ia(prompt)        # AJUSTAR: a função que você já usa em /gerar-loot
    dados = json.loads(texto.replace("```json", "").replace("```", "").strip())

    supabase.table("regioes").update({"descricao": dados["descricao"]}).eq("id", regiao_id).execute()
    novos = []
    for c in dados.get("cidades", []):
        r = supabase.table("locations").insert({
            "campaign_id": g["campaign_id"], "name": c["nome"], "type": "cidade",
            "description": c["descricao"], "regiao_id": regiao_id, "is_homebrew": True,
        }).execute()
        novos.append(r.data[0])
    return {"success": True, "descricao": dados["descricao"], "cidades": novos}