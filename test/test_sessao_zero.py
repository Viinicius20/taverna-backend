from sessao_zero_regras import (LIMITE_RESPOSTA, MAX_GANCHOS, MAX_NPCS,
                                limpar_respostas, validar_proposta)

ID = "11111111-1111-1111-1111-111111111111"


def test_respostas_ignora_chaves_desconhecidas_e_limita_tamanho():
    r = limpar_respostas({"grupo": "a" * 1000, "hack": "x", "medo": 5})
    assert list(r) == ["grupo"]
    assert len(r["grupo"]) == LIMITE_RESPOSTA


def test_respostas_viram_linha_unica():
    assert limpar_respostas({"medo": "linha 1\n\nlinha 2"}) == {"medo": "linha 1 linha 2"}


def test_vinculos_com_referencia_ou_tipo_invalido_sao_descartados():
    bruto = {"npcs": [{"chave": "n1", "nome": "Aldren"}], "vinculos": [
        {"de": f"character:{ID}", "para": "npc:n1", "tipo": "teme"},
        {"de": "character:outro", "para": "npc:n1", "tipo": "teme"},
        {"de": f"character:{ID}", "para": "npc:n9", "tipo": "teme"},
        {"de": f"character:{ID}", "para": "npc:n1", "tipo": "inventado"},
        {"de": f"character:{ID}", "para": "npc:n1", "tipo": ["lista"]},
    ]}
    assert len(validar_proposta(bruto, {ID})["vinculos"]) == 1


def test_quantidades_sao_limitadas():
    bruto = {"ganchos": [{"titulo": f"g{i}"} for i in range(50)],
             "npcs": [{"chave": f"n{i}", "nome": f"N{i}"} for i in range(50)]}
    p = validar_proposta(bruto, set())
    assert len(p["ganchos"]) == MAX_GANCHOS and len(p["npcs"]) == MAX_NPCS


def test_aceita_lixo_sem_quebrar():
    vazio = {"ganchos": [], "npcs": [], "vinculos": [], "fatos": []}
    assert validar_proposta("texto", set()) == vazio
    assert validar_proposta({"ganchos": "x", "npcs": None, "vinculos": {"a": 1}}, set()) == vazio

def test_fatos_sem_destinatario_valido_sao_descartados():
    bruto = {"fatos": [
        {"texto": "a", "para": "todos"},
        {"texto": "b", "para": [f"character:{ID}"]},
        {"texto": "c", "para": ["character:outro"]},
        {"texto": "d"},
        {"texto": "e", "para": "ninguem"},
    ]}
    f = validar_proposta(bruto, {ID})["fatos"]
    assert [x["texto"] for x in f] == ["a", "b"]
    assert f[0]["todos"] is True
    assert f[1]["personagens"] == [ID]