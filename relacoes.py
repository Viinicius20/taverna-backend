TIPO_REL = {"npc": "npc", "local": "location"}


def vinculos_brutos(campaign_id: str, tipo_rel: str, entidade_id: str):
    """Vínculos em que a entrada aparece, com o nome do outro lado. Sem filtro de visibilidade."""
    eid = str(entidade_id)
    base = supabase.table("relationships").select("*").eq("campaign_id", campaign_id)
    como_origem = base.eq("source_type", tipo_rel).eq("source_id", eid).execute().data or []
    como_alvo = (supabase.table("relationships").select("*").eq("campaign_id", campaign_id)
                 .eq("target_type", tipo_rel).eq("target_id", eid).execute().data or [])

    lista = [("saida", a, a["target_type"], str(a["target_id"])) for a in como_origem]
    lista += [("entrada", a, a["source_type"], str(a["source_id"])) for a in como_alvo]

    ids = {t: set() for t in TABELAS}
    for _, _, t, i in lista:
        if t in ids:
            ids[t].add(i)

    nomes = {}
    for t, conjunto in ids.items():
        if not conjunto:
            continue
        rows = supabase.table(TABELAS[t]).select(COLUNAS[t]).in_("id", list(conjunto)).execute().data or []
        for r in rows:
            d = r.get("data") or {}
            nomes[(t, str(r["id"]))] = d.get("name") or r.get("name") or "(sem nome)"

    saida = []
    for direcao, a, t, i in lista:
        nome = nomes.get((t, i))
        if not nome:
            continue
        saida.append({"id": a["id"], "kind": a["kind"], "direcao": direcao,
                      "nota": a.get("note") or "", "secreto": bool(a.get("secret")),
                      "outro_tipo": t, "outro_id": i, "nome": nome})
    return saida