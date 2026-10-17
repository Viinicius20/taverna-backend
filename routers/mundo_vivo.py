from auth import MESTRE
from core import supabase
from datetime import datetime
from fastapi import APIRouter
from fastapi import Body
from fastapi import HTTPException
from ia import gerar_texto_com_gemini
from pydantic import BaseModel
from servicos import propagar_consequencias_evento
from typing import Optional
import json

router = APIRouter()


class ConsequenciaSugerirReq(BaseModel):
    gatilho: str


class WorldEventRequest(BaseModel):
    campaign_id: str
    name: str
    description: str = ""
    deadline: str = ""
    consequences: str = ""
    next_event_name: str = ""
    next_event_description: str = ""
    affects_faction_id: str = ""
    faction_reputation_change: str = ""
    sets_flag_key: str = ""


class UpdateWorldEventRequest(BaseModel):
    progress: int = None
    status: str = None
    locked_by_master: bool = None
    name: str = None
    description: str = None
    deadline: str = None
    consequences: str = None


class FlagRequest(BaseModel):
    campaign_id: str
    key: str
    value: bool = False
    description: str = ""


class UpdateFlagRequest(BaseModel):
    value: bool


class ProphecyRequest(BaseModel):
    campaign_id: str = "00000000-0000-0000-0000-000000000001"
    texto: str
    condicao: str


class UpdateProphecyRequest(BaseModel):
    status: str = None
    notas_cumprimento: str = None


class ConsequenciaCriarReq(BaseModel):
    campaign_id: str
    gatilho: str
    consequencia: Optional[str] = None
    condicao_tipo: str = "manual"   # manual | sessao | flag
    condicao_valor: Optional[str] = None


class ConsequenciaGerarReq(BaseModel):
    gatilho: str


class ConsequenciaRevelarReq(BaseModel):
    enviar_sussurro: bool = False
    personagem_ids: Optional[list[str]] = None


@router.get("/world-log/{campaign_id}", dependencies=MESTRE)
async def listar_world_log(campaign_id: str):
    result = supabase.table("world_log").select("*").eq("campaign_id", campaign_id).order("created_at", desc=True).execute()
    return {"success": True, "data": result.data}


@router.delete("/world-log/{log_id}", dependencies=MESTRE)
def deletar_world_log(log_id: str):
    resp = supabase.table("world_log").delete().eq("id", log_id).execute()
    if not resp.data:
        raise HTTPException(404, "Registro não encontrado")
    return {"ok": True}


@router.post("/consequencias/sugerir", dependencies=MESTRE)
def sugerir_consequencias(req: ConsequenciaSugerirReq):
    prompt = f"""Você é um mestre de D&D 5e criando ganchos narrativos de longo prazo.
Ação dos jogadores: "{req.gatilho}"

Proponha exatamente 3 consequências ocultas DIFERENTES entre si, que só serão reveladas mais tarde, nesta ordem:
1) uma social ou política (reputação, alianças, facções, poder);
2) uma misteriosa ou sobrenatural (algo escondido que reage à ação);
3) uma pessoal ou material (alguém próximo, um item, uma perda ou dívida).

Cada uma com 1-2 frases, ligada de forma causal à ação, e impossível de os jogadores preverem.
Retorne APENAS um JSON válido: um array com 3 strings. Sem markdown."""

    texto = gerar_texto_com_gemini(prompt).strip().replace("```json", "").replace("```", "").strip()

    opcoes = None
    try:
        parsed = json.loads(texto)
        if isinstance(parsed, list):
            opcoes = [str(x).strip() for x in parsed if str(x).strip()]
    except Exception:
        pass

    if not opcoes:
        opcoes = [
            l.strip().strip('[]",\'-•* ').lstrip("0123456789.) ").strip()
            for l in texto.split("\n")
            if l.strip() and l.strip() not in ("[", "]")
        ]

    if len(opcoes) < 3:
        raise HTTPException(502, "A IA não retornou as 3 opções.")
    return {"data": opcoes[:3]}


@router.post("/world-events", dependencies=MESTRE)
async def criar_evento_mundo(req: WorldEventRequest):
    result = supabase.table("world_events").insert({
        "campaign_id": req.campaign_id,
        "name": req.name,
        "description": req.description,
        "deadline": req.deadline,
        "consequences": req.consequences,
        "next_event_name": req.next_event_name,
        "next_event_description": req.next_event_description,
        "affects_faction_id": req.affects_faction_id or None,
        "faction_reputation_change": req.faction_reputation_change or None,
        "sets_flag_key": req.sets_flag_key or None,
        "progress": 0,
        "status": "ativo"
    }).execute()
    return {"success": True, "data": result.data[0] if result.data else None}


@router.get("/world-events/{campaign_id}", dependencies=MESTRE)
async def listar_eventos_mundo(campaign_id: str):
    result = supabase.table("world_events").select("*").eq("campaign_id", campaign_id).order("created_at").execute()
    return {"success": True, "data": result.data}


@router.delete("/world-events/{event_id}", dependencies=MESTRE)
async def deletar_evento_mundo(event_id: str):
    supabase.table("world_events").delete().eq("id", event_id).execute()
    return {"success": True}


@router.post("/world-events/{event_id}/sugerir", dependencies=MESTRE)
async def sugerir_desdobramento(event_id: str):
    result = supabase.table("world_events").select("*").eq("id", event_id).single().execute()
    evento = result.data
    if not evento:
        raise HTTPException(404, "Evento não encontrado")

    prompt = f"""
    Você é um mestre de RPG ajudando outro mestre a decidir os próximos passos do mundo.

    Evento em andamento:
    Nome: {evento['name']}
    Descrição: {evento.get('description', '')}
    Progresso atual: {evento.get('progress', 0)}%
    Consequências ao concluir: {evento.get('consequences', '')}

    Sugira um desdobramento plausível e específico que poderia acontecer em breve, 
    dado o estado atual deste evento. Seja concreto, algo que o mestre possa usar 
    imediatamente na mesa (uma ação de facção, uma complicação, um sinal de que o 
    evento está avançando).

    Responda em 2-3 frases, direto ao ponto, sem introdução.
    """
    try:
        sugestao = gerar_texto_com_gemini(prompt)
        return {"success": True, "data": sugestao.strip()}
    except Exception as e:
        raise HTTPException(500, f"Erro ao gerar sugestão: {str(e)}")


@router.get("/presagios")
async def get_presagios():
    try:
        res = supabase.table("presagios").select("*").order("created_at", desc=True).execute()
        return {"success": True, "data": res.data}
    except Exception as e:
        raise HTTPException(500, f"Erro ao buscar presságios: {str(e)}")


@router.post("/presagios", dependencies=MESTRE)
async def criar_presagio(data: dict = Body(...)):
    try:
        res = supabase.table("presagios").insert({
            "campaign_id": data.get("campaign_id", "00000000-0000-0000-0000-000000000001"),
            "texto": data.get("texto"),
            "cumprido": False
        }).execute()
        return {"success": True, "data": res.data[0]}
    except Exception as e:
        raise HTTPException(500, f"Erro ao criar presságio: {str(e)}")


@router.patch("/presagios/{id}/cumprir", dependencies=MESTRE)
async def cumprir_presagio(id: str):
    try:
        res = supabase.table("presagios").update({"cumprido": True}).eq("id", id).execute()
        return {"success": True, "data": res.data[0]}
    except Exception as e:
        raise HTTPException(500, f"Erro ao cumprir presságio: {str(e)}")


@router.delete("/presagios/{id}", dependencies=MESTRE)
async def deletar_presagio(id: str):
    try:
        supabase.table("presagios").delete().eq("id", id).execute()
        return {"success": True}
    except Exception as e:
        raise HTTPException(500, f"Erro ao deletar presságio: {str(e)}")


@router.patch("/world-events/{event_id}", dependencies=MESTRE)
def atualizar_evento_mundo(event_id: str, req: UpdateWorldEventRequest):
    updates = {k: v for k, v in req.dict().items() if v is not None}
    if not updates:
        return {"success": True}

    antes = supabase.table("world_events").select("progress, status").eq("id", event_id).limit(1).execute()
    if not antes.data:
        raise HTTPException(404, "Evento não encontrado")
    ja_concluido = (antes.data[0].get("progress") or 0) >= 100

    result = supabase.table("world_events").update(updates).eq("id", event_id).execute()
    evento_atualizado = result.data[0] if result.data else None

    if evento_atualizado and (evento_atualizado.get("progress") or 0) >= 100 and not ja_concluido:
        propagar_consequencias_evento(evento_atualizado, evento_atualizado["campaign_id"])

        # Se tem um próximo evento configurado, dispara a cadeia
        if evento_atualizado.get("next_event_name") and not evento_atualizado.get("triggered_event_id"):
            novo_evento = supabase.table("world_events").insert({
                "campaign_id": evento_atualizado["campaign_id"],
                "name": evento_atualizado["next_event_name"],
                "description": evento_atualizado.get("next_event_description", ""),
                "progress": 0,
                "status": "ativo"
            }).execute()

            if novo_evento.data:
                supabase.table("world_events").update({
                    "triggered_event_id": novo_evento.data[0]["id"]
                }).eq("id", event_id).execute()

    return {"success": True}


@router.get("/world-changelog/{campaign_id}/nao-lido/{personagem_id}")
def changelog_nao_lido(campaign_id: str, personagem_id: str):
    resp = supabase.table("world_changelog").select("*") \
        .eq("campaign_id", campaign_id) \
        .order("created_at", desc=True).limit(5).execute()
    nao_lidos = [c for c in resp.data if personagem_id not in (c.get("visto_por") or [])]
    return {"data": nao_lidos}


@router.post("/world-changelog/{changelog_id}/marcar-lido")
def marcar_changelog_lido(changelog_id: str, personagem_id: str = Body(..., embed=True)):
    item = supabase.table("world_changelog").select("*").eq("id", changelog_id).single().execute().data
    if not item:
        raise HTTPException(404, "Changelog não encontrado")
    visto = item.get("visto_por") or []
    if personagem_id not in visto:
        visto.append(personagem_id)
    supabase.table("world_changelog").update({"visto_por": visto}).eq("id", changelog_id).execute()
    return {"ok": True}


@router.get("/world-changelog/{campaign_id}", dependencies=MESTRE)
def listar_changelog(campaign_id: str):
    """Histórico completo — usado pelo mestre no MundoVivo."""
    resp = supabase.table("world_changelog").select("*") \
        .eq("campaign_id", campaign_id) \
        .order("created_at", desc=True).execute()
    return {"data": resp.data}


@router.post("/world-changelog/{changelog_id}/marcar-lido-mestre", dependencies=MESTRE)
def marcar_changelog_lido_mestre(changelog_id: str):
    supabase.table("world_changelog").update({"visto_mestre": True}).eq("id", changelog_id).execute()
    return({"ok": True})


@router.post("/flags", dependencies=MESTRE)
async def criar_flag(req: FlagRequest):
    try:
        result = supabase.table("campaign_flags").insert({
            "campaign_id": req.campaign_id,
            "key": req.key,
            "value": req.value,
            "description": req.description
        }).execute()
        return {"success": True, "data": result.data[0] if result.data else None}
    except Exception as e:
        raise HTTPException(500, f"Erro ao criar flag: {str(e)}")


@router.get("/flags/{campaign_id}", dependencies=MESTRE)
async def listar_flags(campaign_id: str):
    result = supabase.table("campaign_flags").select("*").eq("campaign_id", campaign_id).order("key").execute()
    return {"success": True, "data": result.data}


@router.patch("/flags/{flag_id}", dependencies=MESTRE)
async def atualizar_flag(flag_id: str, req: UpdateFlagRequest):
    supabase.table("campaign_flags").update({"value": req.value}).eq("id", flag_id).execute()
    return {"success": True}


@router.delete("/flags/{flag_id}", dependencies=MESTRE)
async def deletar_flag(flag_id: str):
    supabase.table("campaign_flags").delete().eq("id", flag_id).execute()
    return {"success": True}


@router.post("/prophecies", dependencies=MESTRE)
async def criar_profecia(req: ProphecyRequest):
    result = supabase.table("prophecies").insert({
        "campaign_id": req.campaign_id,
        "texto": req.texto,
        "condicao": req.condicao,
        "status": "pendente"
    }).execute()
    return {"success": True, "data": result.data[0] if result.data else None}


@router.get("/prophecies/{campaign_id}", dependencies=MESTRE)
async def listar_profecias(campaign_id: str):
    result = supabase.table("prophecies").select("*").eq("campaign_id", campaign_id).execute()
    return {"success": True, "data": result.data}


@router.patch("/prophecies/{prophecy_id}", dependencies=MESTRE)
async def atualizar_profecia(prophecy_id: str, req: UpdateProphecyRequest):
    updates = {k: v for k, v in req.dict().items() if v is not None}
    supabase.table("prophecies").update(updates).eq("id", prophecy_id).execute()
    return {"success": True}


@router.delete("/prophecies/{prophecy_id}", dependencies=MESTRE)
async def deletar_profecia(prophecy_id: str):
    supabase.table("prophecies").delete().eq("id", prophecy_id).execute()
    return {"success": True}


@router.post("/consequencias/gerar", dependencies=MESTRE)
def gerar_consequencia_v2(req: ConsequenciaGerarReq):
    prompt = f"""Você é um mestre de D&D 5e criando um gancho narrativo de longo prazo.
Ação dos jogadores: "{req.gatilho}"

Crie UMA consequência oculta e interessante dessa ação, que só será revelada mais tarde.
Deve ser algo que os jogadores não podem prever, mas que faça sentido causal com a ação.
2-3 frases. Responda APENAS com o texto da consequência, sem prefixos, sem aspas, sem markdown."""
    texto = gerar_texto_com_gemini(prompt).strip()
    return {"data": texto}


@router.post("/consequencias", dependencies=MESTRE)
def criar_consequencia(req: ConsequenciaCriarReq):
    ultima = supabase.table("sessions").select("session_number") \
        .eq("campaign_id", req.campaign_id).order("session_number", desc=True).limit(1).execute().data
    numero_atual = ultima[0]["session_number"] if ultima else 0

    r = supabase.table("consequencias_ocultas").insert({
        "campaign_id": req.campaign_id,
        "gatilho": req.gatilho,
        "consequencia": req.consequencia,
        "condicao_tipo": req.condicao_tipo,
        "condicao_valor": req.condicao_valor,
        "session_number_criacao": numero_atual,
    }).execute()
    return {"data": r.data[0]}


@router.get("/consequencias/{campaign_id}", dependencies=MESTRE)
def listar_consequencias(campaign_id: str):
    r = supabase.table("consequencias_ocultas").select("*") \
        .eq("campaign_id", campaign_id).order("created_at", desc=True).execute()
    return {"data": r.data}


@router.get("/consequencias/prontas/{campaign_id}", dependencies=MESTRE)
def consequencias_prontas(campaign_id: str):
    """Consequências com condição automática já satisfeita, ainda ocultas."""
    ocultas = supabase.table("consequencias_ocultas").select("*") \
        .eq("campaign_id", campaign_id).eq("status", "oculta").execute().data or []

    ultima = supabase.table("sessions").select("session_number") \
        .eq("campaign_id", campaign_id).order("session_number", desc=True).limit(1).execute().data
    sessao_atual = ultima[0]["session_number"] if ultima else 0

    flags_ativas = supabase.table("campaign_flags").select("key") \
        .eq("campaign_id", campaign_id).eq("value", True).execute().data or []
    flags_keys = {f["key"] for f in flags_ativas}

    prontas = []
    for c in ocultas:
        if c["condicao_tipo"] == "sessao" and c["condicao_valor"]:
            try:
                if sessao_atual >= int(c["condicao_valor"]):
                    prontas.append(c)
            except ValueError:
                pass
        elif c["condicao_tipo"] == "flag" and c["condicao_valor"] in flags_keys:
            prontas.append(c)

    return {"data": prontas}


@router.post("/consequencias/{cid}/revelar", dependencies=MESTRE)
def revelar_consequencia(cid: str, req: ConsequenciaRevelarReq):
    c = supabase.table("consequencias_ocultas").select("*").eq("id", cid).single().execute().data
    if not c:
        raise HTTPException(404, "Não encontrada")

    supabase.table("consequencias_ocultas").update({
        "status": "revelada",
        "revelada_em": datetime.utcnow().isoformat(),
    }).eq("id", cid).execute()

    supabase.table("world_log").insert({
        "campaign_id": c["campaign_id"],
        "session_number": c.get("session_number_criacao") or 0,
        "event_name": "Consequência revelada",
        "description": f"{c['consequencia']} (originada de: \"{c['gatilho']}\")",
    }).execute()

    if req.enviar_sussurro and req.personagem_ids:
        for pid in req.personagem_ids:
            supabase.table("secret-messages" if False else "secret_messages").insert({
                "campaign_id": c["campaign_id"],
                "character_id": pid,
                "message": f"🕯️ {c['consequencia']}",
            }).execute()

    return {"ok": True}


@router.delete("/consequencias/{cid}", dependencies=MESTRE)
def deletar_consequencia(cid: str):
    supabase.table("consequencias_ocultas").delete().eq("id", cid).execute()
    return {"ok": True}


@router.get("/world-changelog/{campaign_id}/nao-lido-mestre", dependencies=MESTRE)
def changelog_nao_lido_mestre(campaign_id: str):
    r = supabase.table("world_changelog").select("*") \
        .eq("campaign_id", campaign_id).eq("visto_mestre", False) \
        .order("created_at", desc=True).limit(10).execute()
    return {"data": r.data}

