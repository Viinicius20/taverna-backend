import pytest

from motor_dados import ExpressaoInvalida, parse, rolar


def _fila(*valores):
    it = iter(valores)
    return lambda n: next(it)


def test_parse_basico():
    assert parse("2d6+3") == (2, 6, 3)


def test_parse_sem_quantidade_e_negativo():
    assert parse("d20-1") == (1, 20, -1)


@pytest.mark.parametrize("ruim", ["", "abc", "0d6", "21d6", "1d1", "1d101", "2d6+", "1d20+1000"])
def test_expressoes_invalidas(ruim):
    with pytest.raises(ExpressaoInvalida):
        parse(ruim)


def test_total_com_modificador():
    r = rolar("2d6+3", sorteio=_fila(4, 5))
    assert r["dados"]["rolls"] == [4, 5]
    assert r["total"] == 12
    assert r["expressao"] == "2d6+3"


def test_vantagem_fica_com_o_maior():
    r = rolar("1d20+2", "vantagem", _fila(7, 15))
    assert r["dados"]["rolls"] == [15] and r["dados"]["descartados"] == [7]
    assert r["total"] == 17


def test_desvantagem_fica_com_o_menor():
    r = rolar("1d20+2", "desvantagem", _fila(7, 15))
    assert r["dados"]["rolls"] == [7] and r["dados"]["descartados"] == [15]
    assert r["total"] == 9


def test_vantagem_so_vale_para_d20():
    with pytest.raises(ExpressaoInvalida):
        rolar("2d6", "vantagem")