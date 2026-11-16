MOEDAS = ("cobre", "prata", "electro", "ouro", "platina")
TETO = 10_000_000


def aplicar_delta(atual: dict, delta: dict) -> dict:
    """Soma o delta às moedas atuais; nunca fica negativo nem passa do teto."""
    novo = {}
    for k in MOEDAS:
        valor = int(atual.get(k, 0) or 0) + int(delta.get(k, 0) or 0)
        novo[k] = max(0, min(valor, TETO))
    return novo