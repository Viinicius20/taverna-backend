import re
import unicodedata


def normalizar_nome(texto) -> str:
    s = unicodedata.normalize("NFKD", str(texto or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^\w\s]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def chaves_do_local(nome: str) -> set:
    nome = nome or ""
    return {k for k in (normalizar_nome(nome), normalizar_nome(nome.split(",")[0])) if k}


def indice_de_locais(locais: list) -> dict:
    indice = {}
    for l in locais:
        for chave in chaves_do_local(l.get("name")):
            indice.setdefault(chave, str(l["id"]))
    return indice