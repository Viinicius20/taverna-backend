from datetime import datetime, timedelta, timezone

from core import supabase

IGNORAR = {"notas_privadas", "updated_at", "hp_atual", "pv_atual", "hp"}
JANELA_SEGUNDOS = 60


def achatar(valor, prefixo=""):
    if isinstance(valor, dict) and valor:
        saida = {}
        for k, v in valor.items():
            saida.update(achatar(v, f"{prefixo}.{k}" if prefixo else str(k)))
        return saida
    return {prefixo: valor}


def _ignorado(campo):
    return any(parte in IGNORAR for parte in campo.split("."))


def _plano(linha):
    plano = achatar(linha.get("data") or {}) if "data" in linha else {}
    if "name" in linha:
        plano["nome"] = linha["name"]
    return plano


def diff(antigo, novo):
    """Compara só as chaves que vieram em `novo` ('data' e/ou 'name')."""
    chaves = [k for k in ("data", "name") if k in novo]
    a = _plano({k: (antigo or {}).get(k) for k in chaves})
    n = _plano({k: novo[k] for k in chaves})
    mudou = {}
    for campo in a.keys() | n.keys():
        if _ignorado(campo):
            continue
        if a.get(campo) != n.get(campo):
            mudou[campo] = (a.get(campo), n.get(campo))
    return mudou


def registrar_alteracoes(character_id, campaign_id, user_id, antigo, novo):
    """Nunca derruba o salvamento: qualquer erro só vai pro print."""
    try:
        mudancas = diff(antigo, novo)
        if not mudancas:
            return
        agora = datetime.now(timezone.utc)
        desde = (agora - timedelta(seconds=JANELA_SEGUNDOS)).isoformat()
        recentes = (supabase.table("ficha_log").select("id,campo")
                    .eq("character_id", character_id).eq("user_id", user_id)
                    .gte("created_at", desde).execute().data or [])
        por_campo = {r["campo"]: r["id"] for r in recentes}

        novas = []
        for campo, (antes, depois) in mudancas.items():
            if campo in por_campo:
                supabase.table("ficha_log").update(
                    {"valor_novo": depois, "created_at": agora.isoformat()}
                ).eq("id", por_campo[campo]).execute()
            else:
                novas.append({
                    "character_id": character_id,
                    "campaign_id": campaign_id,
                    "user_id": user_id,
                    "campo": campo,
                    "valor_antigo": antes,
                    "valor_novo": depois,
                })
        if novas:
            supabase.table("ficha_log").insert(novas).execute()
    except Exception as e:
        print(f"ERRO HISTORICO: {e}")