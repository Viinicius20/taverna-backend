from utils import limpar_texto

def test_remove_aspas_soltas():
    assert limpar_texto('"Pequena e frágil."') == "Pequena e frágil."

def test_desembrulha_json_aninhado():
    assert limpar_texto('{"description": "Pequenas figuras aladas."}') == "Pequenas figuras aladas."

def test_texto_limpo_fica_igual():
    assert limpar_texto("Texto normal.") == "Texto normal."

def test_valor_que_nao_e_texto_passa_direto():
    assert limpar_texto(None) is None