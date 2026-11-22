from core import supabase

LIMITE_PADRAO = 5
MAX_MOTIVOS = 3


def pressoes_de_reputacao(campaign_id: str) -> list:
    """Lugares onde NPCs suficientes têm relação negativa (ou positiva) com o grupo."""
    try:
        notas = supabase.table("npc_notas").select("npc_id, notas").eq("campaign_id", campaign_id).execute().data or []
        npcs = supabase.table("npcs").select("id, relation_score").eq("campaign_id", campaign_id).execute().data or []
        locais = supabase.table("locations").select("*").eq("campaign_id", campaign_id).execute().data or []
    except Exception:
        return []

    pontos = {str(n["id"]): (n.get("relation_score") or 0) for n in npcs}
    por_local = {}
    for n in notas:
        loc = ((n.get("notas") or {}).get("location") or "").strip().lower()
        if loc and str(n["npc_id"]) in pontos:
            por_local.setdefault(loc, []).append(str(n["npc_id"]))

    resultado = []
    for l in locais:
        nome = (l.get("name") or "").strip()
        ids = por_local.get(nome.lower(), [])
        if not ids:
            continue
        limite = l.get("limite_reputacao") or LIMITE_PADRAO
        for tom, ok in (("negativo", lambda p: p < 0), ("positivo", lambda p: p > 0)):
            do_tom = [i for i in ids if ok(pontos[i])]
            if len(do_tom) >= limite:
                resultado.append({"local": nome, "tom": tom, "qtd": len(do_tom),
                                  "motivos": _motivos(do_tom, tom)})
    return resultado


def _motivos(ids: list, tom: str) -> list:
    try:
        log = (supabase.table("reputation_log").select("reason, delta")
               .eq("entity_type", "npc").in_("entity_id", ids)
               .order("created_at", desc=True).limit(20).execute().data or [])
    except Exception:
        return []
    bate = (lambda d: d < 0) if tom == "negativo" else (lambda d: d > 0)
    motivos = []
    for r in log:
        texto = (r.get("reason") or "").strip()
        if texto and bate(r.get("delta") or 0) and texto not in motivos:
            motivos.append(texto[:160])
        if len(motivos) >= MAX_MOTIVOS:
            break
    return motivos

def fama_dos_personagens(campaign_id: str) -> list:
    """Feitos registrados nos momentos das fichas, para virarem fofoca exagerada."""
    try:
        chars = supabase.table("characters").select("name, data") \
            .eq("campaign_id", campaign_id).execute().data or []
    except Exception:
        return []
    fatos = []
    for c in chars:
        d = c.get("data") or {}
        nome = d.get("name") or c.get("name")
        for m in (d.get("momentos") or [])[-5:]:      # os 5 mais recentes de cada personagem
            texto = (m.get("texto") or "").strip() if isinstance(m, dict) else ""
            if texto:
                fatos.append({"nome": nome, "texto": texto[:200]})
    return fatos