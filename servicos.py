from fastapi import HTTPException
from core import supabase, CAMPANHA_ID
from utils import estado_por_pontos, delta_do_evento, MAXIMO, converter_dia, formatar_data, MESES_PADRAO
import re
import unicodedata
from datetime import datetime

def ajustar_reputacao(tipo: str, entidade_id: str, delta: int, motivo: str, origem: str = "manual") -> dict:
    tabela, coluna = ("factions", "reputation_score") if tipo == "faction" else ("npcs", "relation_score")
    atual = supabase.table(tabela).select(coluna).eq("id", entidade_id).limit(1).execute()
    if not atual.data:
        raise HTTPException(404, "Não encontrado")
    antes = atual.data[0].get(coluna) or 0
    depois = max(-MAXIMO, min(MAXIMO, antes + delta))
    if depois != antes:
        dados = {coluna: depois}
        if tipo == "faction":
            dados["reputation"] = estado_por_pontos(depois)   # o que já lê esse campo continua funcionando
        supabase.table(tabela).update(dados).eq("id", entidade_id).execute()
        supabase.table("reputation_log").insert({
            "campaign_id": CAMPANHA_ID, "entity_type": tipo, "entity_id": entidade_id,
            "delta": depois - antes, "score_after": depois,
            "reason": motivo[:300], "source": origem,
        }).execute()
    return {"pontos": depois, "estado": estado_por_pontos(depois)}

def propagar_consequencias_evento(evento, campaign_id):
    try:
        if evento.get("affects_faction_id") and evento.get("faction_reputation_change"):
            d = delta_do_evento(evento["faction_reputation_change"])
            if d:
                try:
                    ajustar_reputacao("faction", evento["affects_faction_id"], d,
                                      f"Evento: {evento['name']}", "evento")
                except Exception as e:
                    print(f"[AVISO] Falha ao ajustar reputação: {e}")

        if evento.get("sets_flag_key"):
            flag_key = evento["sets_flag_key"]
            existente = supabase.table("campaign_flags").select("id").eq("campaign_id", campaign_id).eq("key", flag_key).execute()

            if existente.data:
                supabase.table("campaign_flags").update({"value": True}).eq("campaign_id", campaign_id).eq("key", flag_key).execute()
            else:
                supabase.table("campaign_flags").insert({
                    "campaign_id": campaign_id,
                    "key": flag_key,
                    "value": True,
                    "description": f"Criada automaticamente pelo evento: {evento['name']}"
                }).execute()
    except Exception as e:
        print(f"[AVISO] Falha ao propagar consequências: {e}")

def normalizar_resposta(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "", t)


def ocultar_cofre(handouts: list, abertos_ids: set) -> list:
    saida = []
    for h in handouts:
        h = dict(h)
        hashes = h.pop("cofre_hashes", None)
        if hashes and h.get("id") not in abertos_ids:
            h["bloqueado"] = True
            h["text_content"] = None
            h["url"] = None
        saida.append(h)
    return saida

def calendario_atual(campaign_id: str) -> dict:
    r = supabase.table("calendario").select("*").eq("campaign_id", campaign_id).limit(1).execute().data
    if r:
        linha = r[0]
    else:
        linha = {"campaign_id": campaign_id, "dia_total": 0, "ano_inicial": 1, "meses": MESES_PADRAO}
        supabase.table("calendario").insert(linha).execute()
    data = converter_dia(linha["dia_total"], linha["meses"], linha["ano_inicial"])
    return {**linha, "data": data, "texto": formatar_data(data)}

def avisar_prazos(campaign_id: str, dia_total: int, texto: str):
    try:
        vencidos = supabase.table("world_events").select("id, name") \
            .eq("campaign_id", campaign_id).eq("status", "ativo").eq("prazo_avisado", False) \
            .lte("data_alvo", dia_total).execute().data or []
        if not vencidos:
            return
        ultima = supabase.table("sessions").select("session_number") \
            .eq("campaign_id", campaign_id).order("session_number", desc=True).limit(1).execute().data
        sessao = ultima[0]["session_number"] if ultima else 0
        for ev in vencidos:
            supabase.table("world_log").insert({
                "campaign_id": campaign_id, "session_number": sessao,
                "event_name": ev["name"],
                "description": f"O prazo de \"{ev['name']}\" chegou ({texto}).",
            }).execute()
            supabase.table("world_events").update({"prazo_avisado": True}).eq("id", ev["id"]).execute()
    except Exception as e:
        print(f"[AVISO] Falha ao avisar prazos: {e}")


def gravar_calendario(campaign_id: str, campos: dict, dias: int, motivo, antes: dict) -> dict:
    campos["updated_at"] = datetime.utcnow().isoformat()
    supabase.table("calendario").update(campos).eq("campaign_id", campaign_id).execute()
    depois = calendario_atual(campaign_id)
    supabase.table("calendario_log").insert({
        "campaign_id": campaign_id, "dias": dias, "motivo": motivo,
        "data_antes": antes["texto"], "data_depois": depois["texto"],
    }).execute()
    avisar_prazos(campaign_id, depois["dia_total"], depois["texto"])
    return depois


def avancar_calendario(campaign_id: str, dias: int, motivo=None) -> dict:
    antes = calendario_atual(campaign_id)
    return gravar_calendario(campaign_id, {"dia_total": antes["dia_total"] + dias}, dias, motivo, antes)