import re
import unicodedata


def normalizar_nome(texto) -> str:
    """'  Éterion,  a Cidade ' -> 'eterion a cidade': sem acento, minúsculas, sem pontuação."""
    s = unicodedata.normalize("NFKD", str(texto or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^\w\s]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def chaves_do_local(nome: str) -> set:
    """O nome inteiro e a parte antes da primeira vírgula ('Éterion, a Cidade...' -> 'Éterion')."""
    nome = nome or ""
    return {k for k in (normalizar_nome(nome), normalizar_nome(nome.split(",")[0])) if k}


def indice_de_locais(locais: list) -> dict:
    """{chave normalizada: id do local}. Se dois locais tiverem a mesma chave, vale o primeiro."""
    indice = {}
    for l in locais:
        for chave in chaves_do_local(l.get("name")):
            indice.setdefault(chave, str(l["id"]))
    return indice