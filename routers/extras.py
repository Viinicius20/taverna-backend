from auth import MESTRE
from auth import exigir_mestre
from core import CAMPANHA_ID
from core import supabase
from datetime import datetime
from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from ia import gerar_texto_com_gemini
from pydantic import BaseModel
from typing import Optional
import json
import random
from servicos import avancar_calendario, calendario_atual

from auth import dono_ou_mestre

router = APIRouter()


ATIVIDADES_DOWNTIME = ["treinar", "trabalhar", "pesquisar", "viajar", "fabricar item", "investigar", "socializar", "descansar"]


CORES_NOTA = {"amarelo", "rosa", "azul", "verde"}


class ArquivoMestreRequest(BaseModel):
    campaign_id: str = "00000000-0000-0000-0000-000000000001"
    categoria: str
    texto: str


class EventoRegional(BaseModel):
    campaign_id: str
    regiao: str
    tipo_evento: str
    motivo: str
    modificadores: dict  # {"comida": 1.5, "armas": 1.3, "viagem": 0.6, "comercio": 0.7}


CHANCE_EVENTO_POR_DIA = 0.35


class IniciarViagem(BaseModel):
    campaign_id: str
    origem_id: str
    destino_id: str
    tempo_estimado_dias: float
    clima: Optional[str] = None


class GazetaGerarReq(BaseModel):
    campaign_id: str
    nome_jornal: Optional[str] = None


class GazetaEditReq(BaseModel):
    titulo: Optional[str] = None
    noticias: Optional[list] = None


class DowntimeSolicitarReq(BaseModel):
    campaign_id: str
    character_id: str
    character_name: str
    atividade: str
    foco: Optional[str] = None


class DowntimeResolverReq(BaseModel):
    consequencia_final: str
    aprovado: bool


class MisterioNovo(BaseModel):
    title: str
    description: str = ""
    clues_total: int = 5
    npc_id: str | None = None
    location_id: str | None = None


class MisterioPistas(BaseModel):
    clues_found: int


class NotaNova(BaseModel):
    text: str
    color: str = "amarelo"
    sessions_left: int | None = None


class NotaEdit(BaseModel):
    done: bool | None = None
    text: str | None = None
    color: str | None = None


@router.post("/arquivo-mestre", dependencies=MESTRE)
async def criar_arquivo_mestre(req: ArquivoMestreRequest):
    result = supabase.table("arquivo_mestre").insert({
        "campaign_id": req.campaign_id,
        "categoria": req.categoria,
        "texto": req.texto
    }).execute()
    return {"success": True, "data": result.data[0] if result.data else None}


@router.get("/arquivo-mestre/{campaign_id}", dependencies=MESTRE)
async def listar_arquivo_mestre(campaign_id: str):
    result = supabase.table("arquivo_mestre").select("*").eq("campaign_id", campaign_id).order("created_at", desc=True).execute()
    return {"success": True, "data": result.data}


@router.delete("/arquivo-mestre/{item_id}", dependencies=MESTRE)
async def deletar_arquivo_mestre(item_id: str):
    supabase.table("arquivo_mestre").delete().eq("id", item_id).execute()
    return {"success": True}


@router.post("/economia/eventos", dependencies=MESTRE)
def criar_evento(evento: EventoRegional):
    resp = supabase.table("eventos_regionais").insert(evento.dict()).execute()
    return resp.data[0]


@router.patch("/economia/eventos/{evento_id}/encerrar", dependencies=MESTRE)
def encerrar_evento(evento_id: str):
    resp = supabase.table("eventos_regionais") \
        .update({"ativo": False}) \
        .eq("id", evento_id).execute()
    if not resp.data:
        raise HTTPException(404, "Evento não encontrado")
    return resp.data[0]


@router.get("/economia/eventos-campanha/{campaign_id}", dependencies=MESTRE)
def listar_todos_eventos(campaign_id: str):
    """Lista todos os eventos regionais (ativos e encerrados) — usado pela aba MundoVivo."""
    resp = supabase.table("eventos_regionais") \
        .select("*") \
        .eq("campaign_id", campaign_id) \
        .order("data_inicio", desc=True) \
        .execute()
    return {"data": resp.data}


@router.get("/economia/precos/{campaign_id}")
def listar_precos_referencia(campaign_id: str):
    """Lista os preços base cadastrados (comida, armas, poções...)."""
    resp = supabase.table("precos_referencia").select("*").eq("campaign_id", campaign_id).execute()
    return {"data": resp.data}


@router.get("/economia/preco/{item_id}")
def preco_atual(item_id: str, regiao: str, campaign_id: str):
    item = supabase.table("precos_referencia").select("*").eq("id", item_id).single().execute().data
    if not item:
        raise HTTPException(404, "Item não encontrado")

    preco_base = item["preco_base"]
    categoria = item["categoria"]

    eventos = listar_todos_eventos(campaign_id)["data"]
    eventos_ativos = [e for e in eventos if e["ativo"] and e["regiao"] == regiao]

    multiplicador_final = 1.0
    motivos = []
    for evento in eventos_ativos:
        mod = evento["modificadores"].get(categoria)
        if mod:
            multiplicador_final *= mod
            motivos.append(evento["motivo"])

    preco_atual = round(preco_base * multiplicador_final, 2)

    return {
        "nome_item": item["nome_item"],
        "preco_atual": preco_atual,
        "preco_normal": preco_base,
        "motivo": " + ".join(motivos) if motivos else None,
    }


@router.delete("/economia/eventos/{evento_id}", dependencies=MESTRE)
def deletar_evento(evento_id: str):
    resp = supabase.table("eventos_regionais").delete().eq("id", evento_id).execute()
    if not resp.data:
        raise HTTPException(404, "Evento não encontrado")
    return {"ok": True}


@router.get("/viagem/locais/{campaign_id}", dependencies=MESTRE)
def listar_locais_para_viagem(campaign_id: str):
    resp = supabase.table("locations").select("id, name, region_info, monsters, commerce") \
        .eq("campaign_id", campaign_id).execute()
    return {"data": resp.data}


@router.post("/viagem/iniciar", dependencies=MESTRE)
def iniciar_viagem(payload: IniciarViagem):
    viagem = payload.dict()
    resp = supabase.table("viagens").insert(viagem).execute()
    return resp.data[0]


@router.post("/viagem/{viagem_id}/avancar", dependencies=MESTRE)
def avancar_dia(viagem_id: str):
    viagem = supabase.table("viagens").select("*").eq("id", viagem_id).single().execute().data
    if not viagem:
        raise HTTPException(404, "Viagem não encontrada")
    if viagem["status"] != "em_andamento":
        raise HTTPException(400, "Viagem já finalizada")

    dia_atual = viagem["dia_atual"] + 1
    eventos = viagem["eventos"] or []

    if random.random() < CHANCE_EVENTO_POR_DIA:
        origem = supabase.table("locations").select("*").eq("id", viagem["origem_id"]).single().execute().data
        destino = supabase.table("locations").select("*").eq("id", viagem["destino_id"]).single().execute().data

        ja_aconteceu = "\n".join(f"- {e['descricao']}" for e in eventos) or "nenhum ainda"

        prompt = (
            f"Gere um evento curto (1-2 frases) de estrada para uma viagem de D&D 5e, "
            f"entre '{origem['name']}' e '{destino['name']}'.\n"
            f"Contexto da região: {destino.get('region_info') or origem.get('region_info') or 'desconhecido'}.\n"
            f"Ameaças possíveis na área: {destino.get('monsters') or origem.get('monsters') or 'nenhuma informada'}.\n"
            f"Comércio/recursos da região: {destino.get('commerce') or origem.get('commerce') or 'nenhum informado'}.\n"
            f"Clima: {viagem.get('clima') or 'não especificado'}.\n"
            f"Eventos que JÁ aconteceram nesta viagem (não repita o mesmo tipo de situação):\n{ja_aconteceu}\n"
            f"Pode ser perigo, encontro, achado ou obstáculo — varie o tipo em relação aos anteriores. "
            f"Não resolva o evento, apenas descreva a situação para o Mestre decidir o que fazer."
        )

        try:
            descricao = gerar_texto_com_gemini(prompt).strip()
            eventos.append({"dia": dia_atual, "descricao": descricao, "resolvido": False})
        except Exception:
            pass

    status = "concluida" if dia_atual >= viagem["tempo_estimado_dias"] else "em_andamento"

    resp = supabase.table("viagens").update({
        "dia_atual": dia_atual,
        "eventos": eventos,
        "status": status,
    }).eq("id", viagem_id).execute()

    try:
        avancar_calendario(viagem["campaign_id"], 1, "Viagem")
    except Exception as e:
        print(f"[AVISO] Falha ao avançar o calendário: {e}")

    return resp.data[0]


@router.get("/viagem/campanha/{campaign_id}", dependencies=MESTRE)
def listar_viagens(campaign_id: str):
    resp = supabase.table("viagens") \
        .select("*, origem:origem_id(name), destino:destino_id(name)") \
        .eq("campaign_id", campaign_id) \
        .order("criado_em", desc=True) \
        .execute()
    return {"data": resp.data}


@router.get("/viagem/{viagem_id}", dependencies=MESTRE)
def status_viagem(viagem_id: str):
    resp = supabase.table("viagens").select("*").eq("id", viagem_id).single().execute()
    if not resp.data:
        raise HTTPException(404, "Viagem não encontrada")
    return resp.data


@router.delete("/viagem/{viagem_id}", dependencies=MESTRE)
def deletar_viagem(viagem_id: str):
    resp = supabase.table("viagens").delete().eq("id", viagem_id).execute()
    if not resp.data:
        raise HTTPException(404, "Viagem não encontrada")
    return {"ok": True}


@router.post("/gazeta/gerar", dependencies=MESTRE)
def gerar_gazeta(req: GazetaGerarReq):
    cid = req.campaign_id
    partes = []

    eventos = supabase.table("world_events").select("name, description, progress, status") \
        .eq("campaign_id", cid).execute().data or []
    ativos = [e for e in eventos if e["status"] == "ativo"]
    concluidos = [e for e in eventos if e["status"] == "concluido"][-5:]
    if ativos:
        partes.append("Eventos em andamento:\n" + "\n".join(
            f"- {e['name']} ({e.get('progress', 0)}%): {e.get('description') or ''}" for e in ativos))
    if concluidos:
        partes.append("Eventos recém-concluídos:\n" + "\n".join(
            f"- {e['name']}: {e.get('description') or ''}" for e in concluidos))

    log = supabase.table("world_log").select("event_name, description") \
        .eq("campaign_id", cid).order("created_at", desc=True).limit(8).execute().data or []
    if log:
        partes.append("Acontecimentos recentes:\n" + "\n".join(f"- {l['description']}" for l in log))

    regionais = supabase.table("eventos_regionais").select("regiao, tipo_evento, motivo, modificadores") \
        .eq("campaign_id", cid).eq("ativo", True).execute().data or []
    if regionais:
        linhas = []
        for r in regionais:
            mods = ", ".join(
                f"{k} {round((v - 1) * 100):+d}%" for k, v in (r["modificadores"] or {}).items() if v and v != 1
            )
            linhas.append(f"- {r['regiao']}: {r['tipo_evento']} ({r['motivo']}). Preços/comércio: {mods or 'sem mudança'}")
        partes.append("Economia e situação regional:\n" + "\n".join(linhas))

    faccoes = supabase.table("factions").select("name, type, reputation") \
        .eq("campaign_id", cid).execute().data or []
    if faccoes:
        partes.append("Facções: " + "; ".join(f"{f['name']} ({f.get('type') or '?'})" for f in faccoes))

    if not partes:
        raise HTTPException(400, "Não há nada no mundo pra noticiar ainda.")

    anteriores = supabase.table("gazetas").select("noticias, edicao") \
        .eq("campaign_id", cid).order("created_at", desc=True).limit(1).execute().data
    nao_repetir = ""
    if anteriores:
        nao_repetir = "Notícias da edição anterior (não repita, só traga desdobramentos):\n" + "\n".join(
            f"- {n.get('texto', '')}" for n in (anteriores[0]["noticias"] or []))

    nome = req.nome_jornal or "Gazeta do Reino"
    texto_data = calendario_atual(cid)["texto"]
    contexto = f"Data de hoje no mundo: {texto_data}\n\n" + "\n\n".join(partes)

    prompt = f"""Você é o redator de "{nome}", um jornal de um mundo de fantasia medieval.
Com base no estado do mundo abaixo, escreva de 4 a 6 notícias curtas (1-2 frases cada), como leria
o povo comum: manchetes do dia, boatos, avisos, variações de preço no mercado.

REGRAS:
- Apenas informação PÚBLICA. Não revele segredos, motivações ocultas nem consequências futuras.
  Se algo for incerto, escreva como rumor ("dizem que...", "há quem afirme...").
- Não invente fatos que contradigam o estado do mundo.
- Preços: use exatamente as variações percentuais informadas.
- Tom de jornal de época, envolvente, sem listas secas.
- Escolha um emoji de ícone adequado para cada notícia.

ESTADO DO MUNDO:
{contexto}

{nao_repetir}

Retorne APENAS um JSON válido:
{{"titulo": "Manchete principal da edição", "noticias": [{{"icone": "⚔️", "texto": "..."}}]}}"""

    try:
        raw = gerar_texto_com_gemini(prompt).strip().replace("```json", "").replace("```", "").strip()
        dados = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(502, "A IA não retornou um JSON válido.")

    edicao = (anteriores[0]["edicao"] if anteriores else 0) + 1
    r = supabase.table("gazetas").insert({
        "campaign_id": cid,
        "titulo": dados.get("titulo") or nome,
        "edicao": edicao,
        "noticias": dados.get("noticias") or [],
        "status": "rascunho",
        "data_mundo": texto_data,
    }).execute()
    return {"data": r.data[0]}


@router.get("/gazeta/{campaign_id}", dependencies=MESTRE)
def listar_gazetas(campaign_id: str):
    r = supabase.table("gazetas").select("*").eq("campaign_id", campaign_id) \
        .order("created_at", desc=True).execute()
    return {"data": r.data}


@router.get("/gazeta/{campaign_id}/publicada")
def gazeta_publicada(campaign_id: str):
    r = supabase.table("gazetas").select("*").eq("campaign_id", campaign_id) \
        .eq("status", "publicada").order("published_at", desc=True).limit(1).execute()
    return {"data": r.data[0] if r.data else None}


@router.patch("/gazeta/{gazeta_id}", dependencies=MESTRE)
def editar_gazeta(gazeta_id: str, req: GazetaEditReq):
    campos = {k: v for k, v in req.dict().items() if v is not None}
    if not campos:
        raise HTTPException(400, "Nada pra atualizar")
    r = supabase.table("gazetas").update(campos).eq("id", gazeta_id).execute()
    return {"data": r.data[0] if r.data else None}


@router.post("/gazeta/{gazeta_id}/publicar", dependencies=MESTRE)
def publicar_gazeta(gazeta_id: str):
    r = supabase.table("gazetas").update({
        "status": "publicada",
        "published_at": datetime.utcnow().isoformat()
    }).eq("id", gazeta_id).execute()
    if not r.data:
        raise HTTPException(404, "Gazeta não encontrada")
    return {"data": r.data[0]}


@router.delete("/gazeta/{gazeta_id}", dependencies=MESTRE)
def deletar_gazeta(gazeta_id: str):
    supabase.table("gazetas").delete().eq("id", gazeta_id).execute()
    return {"ok": True}


@router.post("/downtime/solicitar")
def solicitar_downtime(req: DowntimeSolicitarReq):
    if req.atividade not in ATIVIDADES_DOWNTIME:
        raise HTTPException(400, "Atividade inválida")

    prompt = f"""Você é um mestre de D&D 5e narrando o downtime entre sessões.
Personagem: {req.character_name}.
Atividade escolhida: {req.atividade}.
{f'Detalhe dado pelo jogador: {req.foco}' if req.foco else ''}

Escreva uma consequência curta (2-3 frases) e interessante para essa atividade,
como um resultado narrativo que o Mestre pode ajustar antes de confirmar.
Pode ser positiva, neutra ou trazer uma complicação leve — evite exageros que
mudem drasticamente a campanha sem intervenção do Mestre.
Responda APENAS com o texto da consequência, sem prefixos, sem aspas, sem markdown."""

    try:
        sugestao = gerar_texto_com_gemini(prompt).strip()
    except Exception:
        sugestao = ""

    r = supabase.table("downtime_requests").insert({
        "campaign_id": req.campaign_id,
        "character_id": req.character_id,
        "character_name": req.character_name,
        "atividade": req.atividade,
        "foco": req.foco,
        "consequencia_sugerida": sugestao,
    }).execute()
    return {"data": r.data[0]}


@router.get("/downtime/pendentes/{campaign_id}", dependencies=MESTRE)
def listar_downtime_pendentes(campaign_id: str):
    r = supabase.table("downtime_requests").select("*") \
        .eq("campaign_id", campaign_id).eq("status", "pendente") \
        .order("created_at").execute()
    return {"data": r.data}


@router.post("/downtime/{req_id}/resolver", dependencies=MESTRE)
def resolver_downtime(req_id: str, req: DowntimeResolverReq):
    r = supabase.table("downtime_requests").update({
        "status": "aprovado" if req.aprovado else "rejeitado",
        "consequencia_final": req.consequencia_final,
        "resolvido_em": datetime.utcnow().isoformat(),
    }).eq("id", req_id).execute()
    if not r.data:
        raise HTTPException(404, "Solicitação não encontrada")
    return {"data": r.data[0]}


@router.get("/downtime/resolvidos-nao-vistos/{character_id}", dependencies=[Depends(dono_ou_mestre)])
def downtime_nao_vistos(character_id: str):
    r = supabase.table("downtime_requests").select("*") \
        .eq("character_id", character_id).neq("status", "pendente").eq("visto_jogador", False) \
        .order("resolvido_em", desc=True).execute()
    return {"data": r.data}


@router.post("/downtime/{req_id}/marcar-visto")
def marcar_downtime_visto(req_id: str):
    supabase.table("downtime_requests").update({"visto_jogador": True}).eq("id", req_id).execute()
    return {"ok": True}


@router.get("/misterios", dependencies=[Depends(exigir_mestre)])
def listar_misterios():
    res = supabase.table("mysteries").select("*, npcs(name), locations(name)") \
        .eq("campaign_id", CAMPANHA_ID).order("created_at", desc=True).execute()
    return {"success": True, "data": res.data or []}


@router.post("/misterios", dependencies=[Depends(exigir_mestre)])
def criar_misterio(body: MisterioNovo):
    titulo = body.title.strip()
    if not titulo:
        raise HTTPException(400, "Título obrigatório")
    res = supabase.table("mysteries").insert({
        "campaign_id": CAMPANHA_ID,
        "title": titulo[:200],
        "description": body.description.strip()[:2000],
        "clues_total": max(1, min(body.clues_total, 50)),
        "npc_id": body.npc_id or None,
        "location_id": body.location_id or None,
    }).execute()
    return {"success": True, "data": res.data[0]}


@router.put("/misterios/{misterio_id}/pistas", dependencies=[Depends(exigir_mestre)])
def atualizar_pistas(misterio_id: str, body: MisterioPistas):
    atual = supabase.table("mysteries").select("clues_total") \
        .eq("id", misterio_id).eq("campaign_id", CAMPANHA_ID).limit(1).execute()
    if not atual.data:
        raise HTTPException(404, "Mistério não encontrado")
    total = atual.data[0]["clues_total"]
    found = max(0, min(body.clues_found, total))
    res = supabase.table("mysteries").update({
        "clues_found": found,
        "status": "resolvido" if found >= total else "aberto",
    }).eq("id", misterio_id).eq("campaign_id", CAMPANHA_ID).execute()
    return {"success": True, "data": res.data[0]}


@router.delete("/misterios/{misterio_id}", dependencies=[Depends(exigir_mestre)])
def deletar_misterio(misterio_id: str):
    supabase.table("mysteries").delete() \
        .eq("id", misterio_id).eq("campaign_id", CAMPANHA_ID).execute()
    return {"success": True}


@router.get("/notas-sessao", dependencies=[Depends(exigir_mestre)])
def listar_notas():
    res = supabase.table("session_notes").select("*") \
        .eq("campaign_id", CAMPANHA_ID).eq("done", False) \
        .order("created_at").execute()
    return {"success": True, "data": res.data or []}


@router.post("/notas-sessao", dependencies=[Depends(exigir_mestre)])
def criar_nota(body: NotaNova):
    texto = body.text.strip()
    if not texto:
        raise HTTPException(400, "Escreva a anotação")
    cor = body.color if body.color in CORES_NOTA else "amarelo"
    sessoes = None if body.sessions_left is None else max(0, min(body.sessions_left, 99))
    res = supabase.table("session_notes").insert({
        "campaign_id": CAMPANHA_ID, "text": texto[:300], "color": cor, "sessions_left": sessoes,
    }).execute()
    return {"success": True, "data": res.data[0]}


@router.patch("/notas-sessao/{nota_id}", dependencies=[Depends(exigir_mestre)])
def editar_nota(nota_id: str, body: NotaEdit):
    updates = {}
    if body.done is not None:
        updates["done"] = body.done
    if body.text is not None:
        t = body.text.strip()
        if not t:
            raise HTTPException(400, "Texto vazio")
        updates["text"] = t[:300]
    if body.color is not None and body.color in CORES_NOTA:
        updates["color"] = body.color
    if updates:
        supabase.table("session_notes").update(updates) \
            .eq("id", nota_id).eq("campaign_id", CAMPANHA_ID).execute()
    return {"success": True}


@router.delete("/notas-sessao/{nota_id}", dependencies=[Depends(exigir_mestre)])
def apagar_nota(nota_id: str):
    supabase.table("session_notes").delete() \
        .eq("id", nota_id).eq("campaign_id", CAMPANHA_ID).execute()
    return {"success": True}


@router.post("/notas-sessao/encerrar-sessao", dependencies=[Depends(exigir_mestre)])
def encerrar_sessao_notas():
    res = supabase.table("session_notes").select("id, sessions_left") \
        .eq("campaign_id", CAMPANHA_ID).eq("done", False).gt("sessions_left", 0).execute()
    for n in res.data or []:
        supabase.table("session_notes").update({"sessions_left": n["sessions_left"] - 1}) \
            .eq("id", n["id"]).execute()
    return {"success": True, "atualizadas": len(res.data or [])}

