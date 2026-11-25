import inspect
import json
import time
from typing import Optional
from utils import estado_por_pontos
from locais_util import indice_de_locais, normalizar_nome

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from auth import MESTRE, usuario_atual
from core import supabase
from ia import gerar_texto_com_gemini
import json
import re

router = APIRouter()

NPC_LOCAL_KEY = "location_id"
COL_TITULO = "titulo"
COL_TEXTO = "descricao"


# ---------- utilidades ----------

async def _ler_imagem_mapa(file: UploadFile):
    dados = await file.read()
    if len(dados) > 10 * 1024 * 1024:
        raise HTTPException(413, "Imagem muito grande (máximo 10 MB).")
    ext = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}.get((file.content_type or "").lower())
    if not ext:
        raise HTTPException(400, "Envie uma imagem JPG, PNG ou WEBP.")
    return dados, ext


def _url_publica_mapa(nome: str) -> str:
    url = supabase.storage.from_("Avatars").get_public_url(nome)
    if isinstance(url, dict):
        url = url.get("publicURL") or url.get("publicUrl") or ""
    return url.rstrip("?")


async def chamar_ia(prompt: str) -> str:
    resultado = gerar_texto_com_gemini(prompt)
    if inspect.isawaitable(resultado):
        resultado = await resultado
    return resultado


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
    linhas = q.execute().data or []
    if user.get("role") != "mestre":
        meus = {c["id"] for c in (supabase.table("characters").select("id")
                .eq("campaign_id", campaign_id).eq("user_id", user["sub"]).execute().data or [])}
        linhas = [d for d in linhas if d["personagem_id"] is None or d["personagem_id"] in meus]
    return {"success": True, "data": linhas}
    return {"success": True, "data": q.execute().data}


@router.post("/descobertas", dependencies=MESTRE)
async def revelar(req: DescobertaIn):
    q = (supabase.table("descobertas").select("id")
         .eq("campaign_id", req.campaign_id).eq("tipo", req.tipo)
         .eq("entidade_id", req.entidade_id))
    q = q.eq("personagem_id", req.personagem_id) if req.personagem_id else q.is_("personagem_id", "null")
    if q.execute().data:
        return {"success": True, "ja_existia": True}
    try:
        r = supabase.table("descobertas").insert(req.dict()).execute()
    except Exception as e:
        if "23505" in str(e) or "duplicate" in str(e).lower():
            return {"success": True, "ja_existia": True}
        raise HTTPException(500, "Erro ao revelar.")
    return {"success": True, "data": r.data}


@router.delete("/descobertas/{descoberta_id}", dependencies=MESTRE)
async def esconder(descoberta_id: str):
    supabase.table("descobertas").delete().eq("id", descoberta_id).execute()
    return {"success": True}


def _ids_descobertos(campaign_id: str, user: dict) -> dict:
    meus = (supabase.table("characters").select("id")
            .eq("campaign_id", campaign_id).eq("user_id", user["sub"]).execute().data)
    meus_ids = {c["id"] for c in meus}
    desc = (supabase.table("descobertas").select("tipo,entidade_id,personagem_id")
            .eq("campaign_id", campaign_id).execute().data)
    por_tipo = {}
    for d in desc:
        # vale se é do grupo todo (personagem_id nulo) ou de um personagem do próprio usuário
        if d["personagem_id"] is None or d["personagem_id"] in meus_ids:
            por_tipo.setdefault(d["tipo"], set()).add(str(d["entidade_id"]))
    return por_tipo


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
            "descricao": "", "imagem": r.get("art_url")}


def _norm_npc(r):
    d = r.get("data") or {}
    return {"id": r["id"], "nome": r.get("name"),
            "subtitulo": d.get("occupation") or d.get("race") or "",
            "descricao": "", "imagem": r.get("avatar_url")}


def _norm_item(r):
    oculto = not r.get("identificado")
    partes = [None if oculto else r.get("rarity"), r.get("type")]
    return {"id": r["id"],
            "nome": (r.get("nome_misterioso") or "Item não identificado") if oculto else r.get("name"),
            "subtitulo": " · ".join(p for p in partes if p),
            "descricao": "" if oculto else (r.get("description") or ""),
            "imagem": None if oculto else r.get("art_url")}

def _norm_regiao(r):
    return {"id": r["id"], "nome": r.get("nome"), "subtitulo": "Terra",
            "descricao": r.get("descricao") or "", "imagem": None}

def _norm_faccao(r):
    return {"id": r["id"], "nome": r.get("name"), "subtitulo": r.get("type") or "",
            "descricao": r.get("description") or "", "imagem": None}


TABELAS = {
    "local":   ("locations",   _norm_local,   "locais"),
    "monstro": ("bestiary",    _norm_monstro, "monstros"),
    "npc":     ("npcs",        _norm_npc,     "npcs"),
    "item":    ("magic_items", _norm_item,    "itens"),
    "regiao":  ("regioes", _norm_regiao, "terras"),
    "faccao": ("factions", _norm_faccao, "faccoes"),
}


@router.get("/enciclopedia/{campaign_id}")
async def enciclopedia(campaign_id: str, user: dict = Depends(usuario_atual)):
    ids_por_tipo = _ids_descobertos(campaign_id, user)

    saida = {}
    for tipo, (tabela, norm, chave) in TABELAS.items():
        if tipo == "monstro":
            linhas = supabase.table("bestiary").select("*").eq("discovered", True).execute().data or []
        else:
            ids = list(ids_por_tipo.get(tipo, []))
            linhas = supabase.table(tabela).select("*").in_("id", ids).execute().data if ids else []
        saida[chave] = sorted((norm(r) for r in linhas), key=lambda x: (x["nome"] or "").lower())

    ALIAS = {"criatura": "monstro"}
    ids_str = {t: {str(i) for i in ids} for t, ids in ids_por_tipo.items()}
    ids_str["monstro"] = {str(m["id"]) for m in saida["monstros"]}

    pags = (supabase.table("wiki_paginas")
            .select("id, titulo, categoria, conteudo, entidade_tipo, entidade_id")
            .eq("campaign_id", campaign_id).eq("revelada", True)
            .execute().data or [])

    visiveis = []
    for p in pags:
        t = p.get("entidade_tipo")
        if t and str(p.get("entidade_id")) not in ids_str.get(ALIAS.get(t, t), set()):
            continue
        visiveis.append(p)

    saida["paginas"] = sorted(visiveis, key=lambda p: (p.get("titulo") or "").lower())
    return {"success": True, "data": saida}


# ---------- atlas ----------

def _npcs_por_local(campaign_id: str, indice: dict, npcs_ok=None) -> dict:
    linhas = (supabase.table("npc_notas").select("npc_id, notas")
              .eq("campaign_id", campaign_id).execute().data or [])
    ids_por_local = {}
    for l in linhas:
        lid = indice.get(normalizar_nome((l.get("notas") or {}).get("location") or ""))
        if not lid:
            continue
        if npcs_ok is not None and str(l["npc_id"]) not in npcs_ok:
            continue
        ids_por_local.setdefault(lid, []).append(l["npc_id"])

    todos = list({i for ids in ids_por_local.values() for i in ids})
    nomes = {}
    if todos:
        for c in supabase.table("npcs").select("id, name").in_("id", todos).execute().data or []:
            nomes[str(c["id"])] = c["name"]

    return {
        lid: [{"id": i, "nome": nomes[str(i)]} for i in ids if str(i) in nomes]
        for lid, ids in ids_por_local.items()
    }


def _faccoes_do_atlas(campaign_id: str, faccoes_ok=None, segredos_ok=None) -> list:
    try:
        facs = (supabase.table("factions").select("id, name, type, reputation_score")
                .eq("campaign_id", campaign_id).execute().data or [])
        presencas = (supabase.table("faccao_presenca").select("faccao_id, regiao_id")
                     .eq("campaign_id", campaign_id).execute().data or [])
        notas = (supabase.table("faccao_notas").select("faccao_id, notas")
                 .eq("campaign_id", campaign_id).execute().data or [])
        segredos = (supabase.table("faccao_segredos").select("id, faccao_id, texto, libera_em")
                    .eq("campaign_id", campaign_id).execute().data or [])
    except Exception as e:
        print(f"[AVISO] Facções do atlas indisponíveis: {e}")
        return []

    publico = {n["faccao_id"]: (n.get("notas") or {}).get("publico", "") for n in notas}
    revelados = segredos_ok or set()
    resultado = []
    for f in facs:
        fid = str(f["id"])
        if faccoes_ok is not None and fid not in faccoes_ok:
            continue
        estado = estado_por_pontos(f.get("reputation_score") or 0)
        itens = []
        for s in segredos:
            if s["faccao_id"] != fid:
                continue
            liberado = (ORDEM_ESTADO.get(estado, 1) >= ORDEM_ESTADO.get(s["libera_em"], 2)
                        or str(s["id"]) in revelados)
            if faccoes_ok is None or liberado:       # o mestre vê todos; o jogador, só os liberados
                itens.append({"id": s["id"], "texto": s["texto"],
                              "libera_em": s["libera_em"], "liberado": liberado})
        resultado.append({
            "id": f["id"], "nome": f["name"], "tipo": f.get("type") or "", "estado": estado,
            "publico": publico.get(fid, ""),
            "regioes": [p["regiao_id"] for p in presencas if p["faccao_id"] == fid],
            "segredos": itens,
        })
    return resultado

def _montar_atlas(campaign_id: str, locais_ok=None, regioes_ok=None, npcs_ok=None,
                  faccoes_ok=None, segredos_ok=None):
    locais = supabase.table("locations").select("*").eq("campaign_id", campaign_id).execute().data
    regioes = supabase.table("regioes").select("*").eq("campaign_id", campaign_id).execute().data
    por_id = {str(r["id"]): r for r in locais}
    por_local = _npcs_por_local(campaign_id, indice_de_locais(locais), npcs_ok)

    def faccao_visivel(r):
        fid = r.get("faction_id")
        return str(fid) if fid and (faccoes_ok is None or str(fid) in faccoes_ok) else None

    pins = [
        {**_norm_local(r), "x": r.get("pin_x"), "y": r.get("pin_y"), "regiao_id": r.get("regiao_id"),
                  "npcs": por_local.get(str(r["id"]), []),
         "faccao_id": faccao_visivel(r)}
        for r in locais
        if locais_ok is None or str(r["id"]) in locais_ok
    ]

    regs = []
    for g in regioes:
        if g.get("cx") is None:
            continue
        descoberta = regioes_ok is None or str(g["id"]) in regioes_ok
        item = {"id": g["id"], "cx": g["cx"], "cy": g["cy"],
                "raio": g.get("raio") or 8, "semente": g.get("semente") or 1,
                "descoberta": descoberta}
        if descoberta:
            loc = por_id.get(str(g["local_id"])) if g.get("local_id") else None
            nl = _norm_local(loc) if loc else None
            item.update({
                "nome": g["nome"],
                "descricao": (nl["descricao"] if nl else None) or g.get("descricao") or "",
                "subtitulo": nl["subtitulo"] if nl else "",
                "imagem_url": g.get("imagem_url") or None,
                "local_id": g.get("local_id"),
                "ambiente": g.get("ambiente") or "floresta",
                "info": {
                    "regiao": loc.get("region_info") if loc else None,
                    "comercio": loc.get("commerce") if loc else None,
                    "idioma": loc.get("language") if loc else None,
                },
            })
        regs.append(item)

    return {"pins": pins, "regioes": regs,
            "faccoes": _faccoes_do_atlas(campaign_id, faccoes_ok, segredos_ok)}


@router.get("/atlas/{campaign_id}")
async def atlas(campaign_id: str, user: dict = Depends(usuario_atual)):
    rev = _ids_descobertos(campaign_id, user)
    return {"success": True, "data": _montar_atlas(
        campaign_id, rev.get("local", set()), rev.get("regiao", set()), rev.get("npc", set()),
        rev.get("faccao", set()), rev.get("segredo", set()))}


@router.get("/atlas-mestre/{campaign_id}", dependencies=MESTRE)
async def atlas_mestre(campaign_id: str):
    return {"success": True, "data": _montar_atlas(campaign_id)}


@router.post("/mapa/{campaign_id}", dependencies=MESTRE)
async def upload_mapa(campaign_id: str, file: UploadFile = File(...)):
    dados, ext = await _ler_imagem_mapa(file)
    nome = f"mapa-{campaign_id}.{ext}"
    try:
        supabase.storage.from_("Avatars").upload(
            nome, dados, {"content-type": file.content_type, "upsert": "true"})
    except Exception as e:
        print(f"ERRO MAPA: {e}")
        raise HTTPException(500, "Erro ao enviar o mapa.")
    # o nome do arquivo é sempre o mesmo, então o ?v= evita a imagem antiga em cache
    url = f"{_url_publica_mapa(nome)}?v={int(time.time())}"
    supabase.table("mapas").upsert({"campaign_id": campaign_id, "imagem_url": url}).execute()
    return {"success": True, "url": url}


class MapaUrlIn(BaseModel):
    url: str


@router.put("/mapa/{campaign_id}/url", dependencies=MESTRE)
async def definir_mapa_url(campaign_id: str, req: MapaUrlIn):
    try:
        supabase.table("mapas").upsert({"campaign_id": campaign_id, "imagem_url": req.url}).execute()
    except Exception as e:
        print(f"ERRO MAPA URL: {e}")
        raise HTTPException(500, f"Erro ao salvar o mapa: {e}")
    return {"success": True}


# ---------- regiões ----------

class RegiaoIn(BaseModel):
    campaign_id: str
    nome: str
    descricao: str = ""
    pontos: list = []
    imagem_url: Optional[str] = None
    cx: Optional[float] = None
    cy: Optional[float] = None
    raio: Optional[float] = None
    semente: Optional[int] = None
    local_id: Optional[str] = None
    ambiente: Optional[str] = None


class RegiaoUpdate(BaseModel):
    nome: Optional[str] = None
    descricao: Optional[str] = None
    pontos: Optional[list] = None
    imagem_url: Optional[str] = None
    cx: Optional[float] = None
    cy: Optional[float] = None
    raio: Optional[float] = None
    semente: Optional[int] = None
    local_id: Optional[str] = None
    ambiente: Optional[str] = None


@router.post("/regioes", dependencies=MESTRE)
async def criar_regiao(req: RegiaoIn):
    r = supabase.table("regioes").insert(req.dict(exclude_none=True)).execute()
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
    texto = await chamar_ia(prompt)
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

@router.get("/descobertas-painel/{campaign_id}", dependencies=MESTRE)
async def painel_descobertas(campaign_id: str):
    desc = (supabase.table("descobertas").select("id, tipo, entidade_id, personagem_id")
            .eq("campaign_id", campaign_id).execute().data or [])
    reveladas = {(d["tipo"], str(d["entidade_id"])): d["id"] for d in desc if d["personagem_id"] is None}

    def consulta(tabela, campos):
        try:
            return supabase.table(tabela).select(campos).eq("campaign_id", campaign_id).execute().data or []
        except Exception as e:
            print(f"[AVISO] Painel de descobertas sem {tabela}: {e}")
            return []

    def item(tipo, r, nome, sub="", aviso=""):
        did = reveladas.get((tipo, str(r["id"])))
        return {"id": r["id"], "nome": nome or "(sem nome)", "subtitulo": sub or "", "aviso": aviso,
                "revelado": did is not None, "descoberta_id": did}

    regioes = consulta("regioes", "id, nome")
    locais = consulta("locations", "id, name, type, regiao_id")
    npcs = consulta("npcs", "id, name, data")
    facs = consulta("factions", "id, name, type")
    segredos = consulta("faccao_segredos", "id, faccao_id, texto")
    wiki = consulta("wiki_entradas", "id, titulo, categoria")

    terras_reveladas = {str(r["id"]) for r in regioes if ("regiao", str(r["id"])) in reveladas}
    nome_fac = {str(f["id"]): f["name"] for f in facs}

    por_tipo = {
        "regiao": [item("regiao", r, r.get("nome"), "Terra") for r in regioes],
        "local": [item("local", l, l.get("name"), (l.get("type") or "").capitalize(),
                       "terra ainda oculta" if l.get("regiao_id") and str(l["regiao_id"]) not in terras_reveladas else "")
                  for l in locais],
        "npc": [item("npc", n, n.get("name"), (n.get("data") or {}).get("occupation", "")) for n in npcs],
        "faccao": [item("faccao", f, f.get("name"), f.get("type") or "") for f in facs],
        "segredo": [item("segredo", s, (s.get("texto") or "")[:80], nome_fac.get(str(s["faccao_id"]), "")) for s in segredos],
        "wiki": [item("wiki", w, w.get("titulo"), w.get("categoria") or "") for w in wiki],
    }
    for lista in por_tipo.values():
        lista.sort(key=lambda x: x["nome"].lower())
    return {"success": True, "data": por_tipo}

def registrar_cronica(campaign_id: str, motivo: str):
    try:
        cal = calendario_atual(campaign_id)   # AJUSTE: importe de onde ele é definido
        supabase.table("calendario_log").insert({
            "campaign_id": campaign_id, "dias": 0, "motivo": motivo,
            "data_antes": cal["texto"], "data_depois": cal["texto"],
        }).execute()
    except Exception as e:
        print(f"[AVISO] Crônica não registrada: {e}")

class ItemCadeia(BaseModel):
    tipo: str          # "local" ou "npc"
    entidade_id: str


class CadeiaIn(BaseModel):
    itens: list[ItemCadeia]


def _ja_reveladas(campaign_id: str) -> set:
    desc = (supabase.table("descobertas").select("tipo, entidade_id, personagem_id")
            .eq("campaign_id", campaign_id).execute().data or [])
    return {(d["tipo"], str(d["entidade_id"])) for d in desc if d["personagem_id"] is None}


@router.get("/descobertas-cadeia/{campaign_id}/{tipo}/{entidade_id}", dependencies=MESTRE)
async def filhos_da_cadeia(campaign_id: str, tipo: str, entidade_id: str):
    if tipo not in ("regiao", "local"):
        raise HTTPException(status_code=400, detail="tipo deve ser 'regiao' ou 'local'")
    reveladas = _ja_reveladas(campaign_id)
    filhos = []

    if tipo == "regiao":
        locais = (supabase.table("locations").select("id, name, type")
                  .eq("campaign_id", campaign_id).eq("regiao_id", entidade_id).execute().data or [])
        for l in locais:
            if ("local", str(l["id"])) not in reveladas:
                filhos.append({"tipo": "local", "entidade_id": str(l["id"]),
                               "nome": l.get("name") or "(sem nome)",
                               "subtitulo": (l.get("type") or "").capitalize()})
    else:
        npcs = (supabase.table("npcs").select("id, name, data")
                .eq("campaign_id", campaign_id).execute().data or [])
        for n in npcs:
            local_atual = (n.get("data") or {}).get(NPC_LOCAL_KEY)
            if local_atual and str(local_atual) == entidade_id and ("npc", str(n["id"])) not in reveladas:
                filhos.append({"tipo": "npc", "entidade_id": str(n["id"]),
                               "nome": n.get("name") or "(sem nome)",
                               "subtitulo": (n.get("data") or {}).get("occupation", "")})

    return {"success": True, "data": filhos}


@router.post("/descobertas-cadeia/{campaign_id}", dependencies=MESTRE)
async def revelar_cadeia(campaign_id: str, body: CadeiaIn):
    permitidos = {"local", "npc"}
    reveladas = _ja_reveladas(campaign_id)
    novos, vistos = [], set()
    for it in body.itens:
        chave = (it.tipo, str(it.entidade_id))
        if it.tipo not in permitidos or chave in reveladas or chave in vistos:
            continue
        vistos.add(chave)
        novos.append({"campaign_id": campaign_id, "tipo": it.tipo,
                      "entidade_id": it.entidade_id, "personagem_id": None})
    contagem = {t: sum(1 for n in novos if n["tipo"] == t) for t in permitidos}
    if novos:
        supabase.table("descobertas").insert(novos).execute()
        rotulos = {"local": ("local", "locais"), "npc": ("NPC", "NPCs")}
        partes = [f"{n} {rotulos[t][0] if n == 1 else rotulos[t][1]}"
                  for t, n in contagem.items() if n]
        registrar_cronica(campaign_id, "Revelado: " + ", ".join(partes))
    return {"success": True, "revelados": len(novos), "por_tipo": contagem}

def _resumo(txt, n=140):
    txt = (txt or "").strip()
    return txt if len(txt) <= n else txt[:n].rstrip() + "…"


def _indice(campaign_id: str, mestre: bool) -> list:
    reveladas = _ja_reveladas(campaign_id)
    desc = (supabase.table("descobertas").select("id, tipo, entidade_id")
            .eq("campaign_id", campaign_id).is_("personagem_id", "null").execute().data or [])
    did_de = {(d["tipo"], str(d["entidade_id"])): d["id"] for d in desc}

    def tabela(nome, campos, por_campanha=True):
        try:
            q = supabase.table(nome).select(campos)
            if por_campanha:
                q = q.eq("campaign_id", campaign_id)
            return q.execute().data or []
        except Exception as e:
            print(f"[AVISO] Índice da wiki sem {nome}: {e}")
            return []

    itens = []

    def add(tipo, r, nome, sub="", resumo="", revelado=None):
        chave = "monstro" if tipo == "criatura" else tipo
        rev = (chave, str(r["id"])) in reveladas if revelado is None else revelado
        if not (mestre or rev):
            return
        itens.append({"tipo": tipo, "id": r["id"], "nome": nome or "(sem nome)",
                      "subtitulo": sub or "", "resumo": _resumo(resumo), "revelado": rev,
                      "descoberta_id": did_de.get((chave, str(r["id"])))})

    for r in tabela("regioes", "id, nome"):
        add("regiao", r, r.get("nome"), "Terra")
    for l in tabela("locations", "id, name, type, description"):
        add("local", l, l.get("name"), (l.get("type") or "").capitalize(), l.get("description"))
    for n in tabela("npcs", "id, name, data"):
        add("npc", n, n.get("name"), (n.get("data") or {}).get("occupation", ""))
    for f in tabela("factions", "id, name, type"):
        add("faccao", f, f.get("name"), f.get("type") or "")
    for b in tabela("bestiary", "id, name, cr, size, type, discovered", por_campanha=False):
        add("criatura", b, b.get("name"),
            f"CR {b.get('cr')} · {b.get('size') or ''} {b.get('type') or ''}".strip(),
            revelado=b.get("discovered") is True)
    for i in tabela("magic_items", "id, name, type, rarity", por_campanha=False):
        add("item", i, i.get("name"), " · ".join(x for x in [i.get("rarity"), i.get("type")] if x),
            revelado=("item", str(i["id"])) in did_de)

    itens.sort(key=lambda x: x["nome"].lower())
    return itens

@router.get("/wiki-indice/{campaign_id}", dependencies=MESTRE)
async def wiki_indice_mestre(campaign_id: str):
    return {"success": True, "data": _indice(campaign_id, True)}

@router.get("/wiki-indice/{campaign_id}/jogador")
async def wiki_indice_jogador(campaign_id: str):
    return {"success": True, "data": _indice(campaign_id, False)}

LORE = {
    "regiao":   [("descricao", "Descrição", False), ("description", "Descrição", False)],
    "local":  [("description", "Descrição", False), ("region_info", "Região", False),
              ("commerce", "Comércio", False), ("language", "Idioma", False),
              ("monsters", "Monstros e perigos", True), ("quests", "Ideias de quest", True),
              ("boss", "Ameaça principal", True)],
    "npc":      [("backstory", "História", False), ("history", "História", False),
                 ("background", "Origem", False), ("description", "Descrição", False),
                 ("appearance", "Aparência", False)],
    "faccao":   [("description", "Descrição", False), ("history", "História", False)],
    "criatura": [("description", "Descrição", False), ("lore", "Lore", False)],
    "item":     [("description", "Descrição", False)],
}
TABELA_DE = {"regiao": "regioes", "local": "locations", "npc": "npcs",
             "faccao": "factions", "criatura": "bestiary", "item": "magic_items"}

def _item(x):
    if isinstance(x, str):
        s = x.strip()
        if s and s[0] in "{[":
            try:
                return _item(json.loads(s))
            except Exception:
                pass
        s = re.sub(r"^\s*\d+[.)]\s*", "", s)
        m = re.match(r"\*\*(.+?)\*\*\s*[:\-–]?\s*(.*)", s, re.S)
        if m:
            return {"titulo": m.group(1).strip().rstrip(":").strip(), "texto": m.group(2).strip()}
        return {"titulo": "", "texto": s.replace("**", "")}
    if isinstance(x, dict):
        titulo = x.get("title") or x.get("titulo") or x.get("name") or x.get("nome") or ""
        texto = (x.get("description") or x.get("descricao") or x.get("desc")
                 or x.get("texto") or x.get("text") or "")
        return {"titulo": str(titulo).strip(), "texto": str(texto).strip()}
    return {"titulo": "", "texto": str(x).strip()}


def _normalizar(valor):
    if isinstance(valor, str):
        s = valor.strip()
        if not s:
            return None
        if s[0] in "[{":
            try:
                valor = json.loads(s)
            except Exception:
                return ("texto", s)
        else:
            return ("texto", s)
    if isinstance(valor, dict):
        valor = [valor]
    if isinstance(valor, list):
        itens = [i for i in (_item(x) for x in valor) if i["titulo"] or i["texto"]]
        return ("itens", itens) if itens else None
    return None

def _detalhe(campaign_id: str, tipo: str, entidade_id: str, mestre: bool):
    if tipo not in TABELA_DE:
        raise HTTPException(status_code=400, detail="Tipo inválido")
    q = supabase.table(TABELA_DE[tipo]).select("*").eq("id", entidade_id)
    if tipo != "criatura":                      # bestiary não tem campaign_id
        q = q.eq("campaign_id", campaign_id)
    rows = q.execute().data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Entrada não encontrada")
    row = rows[0]

    if not mestre:
        visivel = (row.get("discovered") is not False) if tipo == "criatura" \
            else (tipo, str(entidade_id)) in _ja_reveladas(campaign_id)
        if not visivel:
            raise HTTPException(status_code=404, detail="Entrada não encontrada")

    # A terra não guarda texto: quem a descreve é o local ligado a ela (local_id)
    fonte, defs = row, LORE[tipo]
    if tipo == "regiao" and row.get("local_id"):
        loc = (supabase.table("locations").select("*")
               .eq("id", row["local_id"]).eq("campaign_id", campaign_id).execute().data or [])
        if loc:
            fonte, defs = loc[0], LORE["local"]

    data = fonte.get("data") if isinstance(fonte.get("data"), dict) else {}
    campos, vistos = [], set()
    for chave, rotulo, so_mestre in defs:
        if so_mestre and not mestre:
            continue
        if chave in vistos:
            continue
        norm = _normalizar(fonte.get(chave) or data.get(chave))
        if not norm:
            continue
        vistos.add(chave)
        formato, conteudo = norm
        campo = {"chave": chave, "rotulo": rotulo}
        campo["texto" if formato == "texto" else "itens"] = conteudo
        campos.append(campo)

    resp = {"tipo": tipo, "id": row["id"], "campos": campos}
    if mestre:
        todas = {k for k, v in {**fonte, **data}.items() if isinstance(v, str) and v.strip()}
        resp["outras_chaves"] = sorted(todas - {c[0] for c in defs} - {"id", "name", "nome", "campaign_id"})
    return resp


@router.get("/wiki-entidade/{campaign_id}/{tipo}/{entidade_id}", dependencies=MESTRE)
async def wiki_entidade_mestre(campaign_id: str, tipo: str, entidade_id: str):
    return {"success": True, "data": _detalhe(campaign_id, tipo, entidade_id, True)}


@router.get("/wiki-entidade/{campaign_id}/{tipo}/{entidade_id}/jogador")
async def wiki_entidade_jogador(campaign_id: str, tipo: str, entidade_id: str):
    return {"success": True, "data": _detalhe(campaign_id, tipo, entidade_id, False)}