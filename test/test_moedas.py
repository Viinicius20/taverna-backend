from moedas import TETO, aplicar_delta


def test_soma_delta():
    assert aplicar_delta({"ouro": 10}, {"ouro": 5})["ouro"] == 15


def test_nao_fica_negativo():
    assert aplicar_delta({"prata": 3}, {"prata": -10})["prata"] == 0


def test_respeita_o_teto():
    assert aplicar_delta({"ouro": TETO}, {"ouro": 5})["ouro"] == TETO


def test_moedas_ausentes_comecam_em_zero():
    assert aplicar_delta({}, {"platina": 2}) == {
        "cobre": 0, "prata": 0, "electro": 0, "ouro": 0, "platina": 2}


def test_ignora_chaves_desconhecidas():
    assert "diamante" not in aplicar_delta({}, {"diamante": 99})