from historico import diff


def test_detecta_mudanca_simples():
    assert diff({"data": {"nivel": 1}}, {"data": {"nivel": 2}}) == {"nivel": (1, 2)}


def test_ignora_notas_privadas_e_hp():
    antigo = {"data": {"notas_privadas": "a", "hp_atual": 10, "forca": 10}}
    novo = {"data": {"notas_privadas": "b", "hp_atual": 5, "forca": 12}}
    assert diff(antigo, novo) == {"forca": (10, 12)}


def test_sem_mudanca_nao_gera_log():
    d = {"data": {"a": {"b": 1}}}
    assert diff(d, d) == {}


def test_patch_sem_data_nao_apaga_nada():
    assert diff({"data": {"a": 1}, "name": "X"}, {"avatar_url": "u"}) == {}


def test_nome():
    assert diff({"name": "A", "data": {}}, {"name": "B"}) == {"nome": ("A", "B")}