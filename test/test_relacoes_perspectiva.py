from routers.relacoes import filtrar_perspectiva

EU = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
NPC_CONHECIDO = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
NPC_DESCONHECIDO = "cccccccc-cccc-cccc-cccc-cccccccccccc"


def no(tipo, id_):
    return {"id": f"{tipo}:{id_}", "tipo": tipo, "label": tipo}


def aresta(a, b, secreto=False):
    return {"id": f"{a}->{b}", "source": a, "target": b, "kind": "conhece", "note": "", "secret": secreto}


def montar():
    nos = {n["id"]: n for n in [
        no("character", EU), no("npc", NPC_CONHECIDO), no("npc", NPC_DESCONHECIDO), no("faction", "f1"),
    ]}
    eu, ok, nao, fac = f"character:{EU}", f"npc:{NPC_CONHECIDO}", f"npc:{NPC_DESCONHECIDO}", "faction:f1"
    return nos, eu, ok, nao, fac


def test_mostra_npc_conhecido_e_esconde_o_resto():
    nos, eu, ok, nao, fac = montar()
    arestas = [aresta(eu, ok), aresta(eu, nao), aresta(ok, fac)]
    n, a = filtrar_perspectiva(nos, arestas, {NPC_CONHECIDO}, EU)
    assert set(n) == {eu, ok}
    assert [x["id"] for x in a] == [f"{eu}->{ok}"]


def test_vinculo_secreto_nunca_aparece():
    nos, eu, ok, nao, fac = montar()
    n, a = filtrar_perspectiva(nos, [aresta(eu, ok, secreto=True)], {NPC_CONHECIDO}, EU)
    assert a == []
    assert ok not in n


def test_sem_nada_conhecido_sobra_so_o_personagem():
    nos, eu, ok, nao, fac = montar()
    n, a = filtrar_perspectiva(nos, [aresta(eu, nao)], set(), EU)
    assert a == [] and set(n) == {eu}