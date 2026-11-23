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
    # funciona se gerar_texto_com_gemini for comum ou async
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


TABELAS = {
    "local":   ("locations",   _norm_local,   "locais"),
    "monstro": ("bestiary",    _norm_monstro, "monstros"),
    "npc":     ("npcs",        _norm_npc,     "npcs"),
    "item":    ("magic_items", _norm_item,    "itens"),
}


@router.get("/enciclopedia/{campaign_id}")
async def enciclopedia(campaign_id: str, user: dict = Depends(usuario_atual)):
    ids_por_tipo = _ids_descobertos(campaign_id, user)

    saida = {}
    for tipo, (tabela, norm, chave) in TABELAS.items():
        ids = list(ids_por_tipo.get(tipo, []))
        linhas = supabase.table(tabela).select("*").in_("id", ids).execute().data if ids else []
        saida[chave] = sorted((norm(r) for r in linhas), key=lambda x: (x["nome"] or "").lower())

    return {"success": True, "data": saida}


# ---------- atlas ----------

def _npcs_por_local(campaign_id: str, indice: dict, npcs_ok=None) -> dict:
    """{id do local: [{'id', 'nome'}]}. npcs_ok=None: mestre (todos); set: só os revelados."""
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
    """faccoes_ok=None: mestre (tudo). set: só as facções reveladas, com os segredos já liberados."""
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
    """None = mestre (tudo). set = jogador (só o que foi revelado)."""
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
    }
    for lista in por_tipo.values():
        lista.sort(key=lambda x: x["nome"].lower())
    return {"success": True, "data": por_tipo}

def registrar_cronica(campaign_id: str, titulo: str, texto: str = ""):
    """Best-effort: se falhar, a revelação continua funcionando."""
    try:
        cal = calendario_atual(campaign_id)      # importe de onde ele é definido
        data_txt = cal.get("texto", "")
        supabase.table("world_changelog").insert({
            "campaign_id": campaign_id,
            COL_TITULO: titulo,
            COL_TEXTO: f"{texto} ({data_txt})" if data_txt else texto,
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
    """O que pode ser revelado junto: terra -> locais dela; local -> NPCs que estão nele."""
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
    """Revela vários itens de uma vez (um único insert, então ou entra tudo ou nada)."""
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
    if novos:
        supabase.table("descobertas").insert(novos).execute()
        nomes = {"local": ("local", "locais"), "npc": ("NPC", "NPCs")}
        partes = [f"{n} {nomes[t][0] if n == 1 else nomes[t][1]}"
                  for t, n in contagem_de(novos).items() if n]
        registrar_cronica(campaign_id, "O mundo se revela", ", ".join(partes) + " descobertos.")
    return {"success": True, "revelados": len(novos), "por_tipo": contagem}