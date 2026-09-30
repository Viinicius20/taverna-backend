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