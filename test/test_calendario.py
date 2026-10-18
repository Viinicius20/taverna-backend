from utils import converter_dia, para_dia_total, MESES_PADRAO
from routers.calendario import _delta


def test_desfazer_so_o_que_e_reversivel():
    assert _delta({"dias": 7, "motivo": "Viagem"}) == 7
    assert _delta({"dias": 0, "motivo": "Data definida pelo mestre", "dia_antes": 10, "dia_depois": 40}) == 30
    assert _delta({"dias": 0, "motivo": "Data definida pelo mestre"}) is None
    assert _delta({"dias": 0, "motivo": "Meses reconfigurados", "dia_antes": 1, "dia_depois": 2}) is None

def test_ida_e_volta():
    for dia in (0, 29, 30, 359, 360, 1000, 123456):
        d = converter_dia(dia, MESES_PADRAO, 1)
        assert para_dia_total(d["ano"], d["mes"], d["dia"], MESES_PADRAO, 1) == dia


def test_virada_de_ano():
    d = converter_dia(360, MESES_PADRAO, 1000)
    assert (d["ano"], d["mes"], d["dia"]) == (1001, 1, 1)


def test_meses_de_tamanhos_diferentes():
    meses = [{"nome": "A", "dias": 10}, {"nome": "B", "dias": 5}]
    assert converter_dia(10, meses, 1)["mes_nome"] == "B"
    assert converter_dia(15, meses, 1) == {"dia": 1, "mes": 1, "mes_nome": "A", "ano": 2}