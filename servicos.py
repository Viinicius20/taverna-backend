from fastapi import HTTPException
from core import supabase, CAMPANHA_ID
from utils import estado_por_pontos, delta_do_evento, MAXIMO

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