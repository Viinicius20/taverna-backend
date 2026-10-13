from utils import estado_por_pontos, delta_do_evento, LIMIAR, MAXIMO

def test_neutra_no_meio():
    assert estado_por_pontos(0) == "neutra"
    assert estado_por_pontos(49) == "neutra"
    assert estado_por_pontos(-49) == "neutra"

def test_estado_muda_no_limiar():
    assert estado_por_pontos(50) == "aliada"
    assert estado_por_pontos(-50) == "hostil"

def test_delta_numerico():
    assert delta_do_evento("20") == 20
    assert delta_do_evento("-30") == -30

def test_delta_limitado_ao_maximo():
    assert delta_do_evento("999") == MAXIMO
    assert delta_do_evento("-999") == -MAXIMO

def test_delta_valores_antigos():
    assert delta_do_evento("aliada") == LIMIAR
    assert delta_do_evento("hostil") == -LIMIAR
    assert delta_do_evento("neutra") == 0

def test_delta_invalido_vira_zero():
    assert delta_do_evento("abc") == 0
    assert delta_do_evento(None) == 0
    assert delta_do_evento("") == 0