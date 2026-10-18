# utils.py
import json

def limpar_texto(valor):
    if not isinstance(valor, str):
        return valor
    texto = valor.strip()
    for _ in range(2):   # cobre até duas camadas
        if not texto or texto[0] not in '{"':
            break
        try:
            obj = json.loads(texto)
        except json.JSONDecodeError:
            break
        if isinstance(obj, dict):
            obj = next((v for v in obj.values() if isinstance(v, str)), "")
        if not isinstance(obj, str):
            break
        texto = obj.strip()
    return texto.strip('"“”').strip()

LIMIAR = 50
MAXIMO = 100

def estado_por_pontos(pontos: int) -> str:
    if pontos >= LIMIAR:
        return "aliada"
    if pontos <= -LIMIAR:
        return "hostil"
    return "neutra"

def delta_do_evento(valor) -> int:
    v = str(valor or "").strip().lower()
    antigos = {"aliada": LIMIAR, "hostil": -LIMIAR, "neutra": 0}
    if v in antigos:
        return antigos[v]
    try:
        return max(-MAXIMO, min(MAXIMO, int(v)))
    except ValueError:
        return 0

MESES_PADRAO = [
    {"nome": "Primeira Neve", "dias": 30}, {"nome": "Degelo", "dias": 30},
    {"nome": "Semeadura", "dias": 30}, {"nome": "Florada", "dias": 30},
    {"nome": "Sol Alto", "dias": 30}, {"nome": "Estio", "dias": 30},
    {"nome": "Colheita", "dias": 30}, {"nome": "Ceifa", "dias": 30},
    {"nome": "Bruma", "dias": 30}, {"nome": "Chuvas", "dias": 30},
    {"nome": "Sombra", "dias": 30}, {"nome": "Longa Noite", "dias": 30},
]


def converter_dia(dia_total: int, meses: list, ano_inicial: int) -> dict:
    ano_dias = sum(m["dias"] for m in meses)
    ano = ano_inicial + dia_total // ano_dias
    resto = dia_total % ano_dias
    for i, m in enumerate(meses):
        if resto < m["dias"]:
            return {"dia": resto + 1, "mes": i + 1, "mes_nome": m["nome"], "ano": ano}
        resto -= m["dias"]


def para_dia_total(ano: int, mes: int, dia: int, meses: list, ano_inicial: int) -> int:
    ano_dias = sum(m["dias"] for m in meses)
    return (ano - ano_inicial) * ano_dias + sum(m["dias"] for m in meses[:mes - 1]) + (dia - 1)


def formatar_data(d: dict) -> str:
    return f"{d['dia']} de {d['mes_nome']}, ano {d['ano']}"