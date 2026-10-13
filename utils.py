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