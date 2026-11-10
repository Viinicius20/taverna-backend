import re
import secrets

_EXPR = re.compile(r"^\s*(\d{1,2})?[dD](\d{1,3})\s*(?:([+-])\s*(\d{1,3}))?\s*$")


class ExpressaoInvalida(ValueError):
    pass


def parse(expressao):
    m = _EXPR.match(expressao or "")
    if not m:
        raise ExpressaoInvalida("Use o formato 2d6+3")
    qtd = int(m.group(1) or 1)
    lados = int(m.group(2))
    mod = int(m.group(4) or 0) * (-1 if m.group(3) == "-" else 1)
    if not 1 <= qtd <= 20 or not 2 <= lados <= 100:
        raise ExpressaoInvalida("Máximo de 20 dados, de 2 a 100 lados")
    return qtd, lados, mod


def rolar(expressao, modo="normal", sorteio=None):
    qtd, lados, mod = parse(expressao)
    sorteio = sorteio or (lambda n: secrets.randbelow(n) + 1)

    if modo != "normal" and not (qtd == 1 and lados == 20):
        raise ExpressaoInvalida("Vantagem e desvantagem só valem para 1d20")

    if modo == "normal":
        mantidos = [sorteio(lados) for _ in range(qtd)]
        descartados = []
    else:
        a, b = sorteio(20), sorteio(20)
        maior, menor = max(a, b), min(a, b)
        mantidos, descartados = ([maior], [menor]) if modo == "vantagem" else ([menor], [maior])

    texto = f"{qtd}d{lados}" + (f"{mod:+d}" if mod else "")
    return {
        "expressao": texto,
        "dados": {"rolls": mantidos, "descartados": descartados, "lados": lados, "qtd": qtd, "modo": modo},
        "modificador": mod,
        "total": sum(mantidos) + mod,
    }