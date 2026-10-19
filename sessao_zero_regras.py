from utils import limpar_texto

PERGUNTAS = {
    "grupo": "Como seu personagem conhece o grupo?",
    "medo": "De quem (ou do quê) ele tem medo?",
    "divida": "O que ele deve a alguém, ou o que alguém deve a ele?",
    "segredo": "Que segredo ele guarda?",
    "reencontro": "Quem ele gostaria de reencontrar, ou de nunca mais ver?",
}
LIMITE_RESPOSTA = 400
VINCULOS_VALIDOS = {"conhece", "aliado", "rival", "inimigo", "familia", "serve",
                    "lidera", "teme", "deve_favor", "vive_em"}
MAX_GANCHOS, MAX_NPCS, MAX_VINCULOS = 8, 8, 20
MAX_FATOS = 8


def limpar_respostas(bruto) -> dict:
    """Só as perguntas conhecidas, texto em linha única, tamanho limitado."""
    if not isinstance(bruto, dict):
        return {}
    saida = {}
    for chave in PERGUNTAS:
        valor = bruto.get(chave)
        if isinstance(valor, str):
            texto = " ".join(valor.split())[:LIMITE_RESPOSTA]
            if texto:
                saida[chave] = texto
    return saida


def _texto(valor, limite):
    if not isinstance(valor, str):
        return ""
    return " ".join(str(limpar_texto(valor)).split())[:limite]


def _lista(valor):
    return valor if isinstance(valor, list) else []


def _ref(valor, ids_personagens, chaves_npcs):
    if not isinstance(valor, str) or ":" not in valor:
        return None
    tipo, _, ident = valor.partition(":")
    ident = ident.strip()
    if tipo == "character" and ident in ids_personagens:
        return f"character:{ident}"
    if tipo == "npc" and ident in chaves_npcs:
        return f"npc:{ident}"
    return None


def validar_proposta(bruto, ids_personagens) -> dict:
    """Aceita só o que tem forma, tamanho e referências válidas. Serve para a saída da IA e para o que o cliente reenvia."""
    bruto = bruto if isinstance(bruto, dict) else {}

    ganchos = []
    for g in _lista(bruto.get("ganchos"))[:MAX_GANCHOS]:
        if not isinstance(g, dict):
            continue
        titulo = _texto(g.get("titulo"), 80)
        if titulo:
            ganchos.append({"titulo": titulo, "descricao": _texto(g.get("descricao"), 250)})

    npcs, chaves = [], set()
    for n in _lista(bruto.get("npcs"))[:MAX_NPCS]:
        if not isinstance(n, dict):
            continue
        chave, nome = _texto(n.get("chave"), 20), _texto(n.get("nome"), 60)
        if not chave or not nome or chave in chaves:
            continue
        chaves.add(chave)
        npcs.append({
            "chave": chave, "nome": nome,
            "ocupacao": _texto(n.get("ocupacao"), 80),
            "personalidade": _texto(n.get("personalidade"), 250),
            "motivacao": _texto(n.get("motivacao"), 250),
            "aparencia": _texto(n.get("aparencia"), 250),
        })

    vinculos, vistos = [], set()
    for v in _lista(bruto.get("vinculos"))[:MAX_VINCULOS]:
        if not isinstance(v, dict):
            continue
        tipo = v.get("tipo")
        if not isinstance(tipo, str) or tipo not in VINCULOS_VALIDOS:
            continue
        de = _ref(v.get("de"), ids_personagens, chaves)
        para = _ref(v.get("para"), ids_personagens, chaves)
        if not de or not para or de == para or (de, para, tipo) in vistos:
            continue
        vistos.add((de, para, tipo))
        vinculos.append({"de": de, "para": para, "tipo": tipo,
                         "nota": _texto(v.get("nota"), 200), "secreto": v.get("secreto") is not False})

    fatos = []
    for f in _lista(bruto.get("fatos"))[:MAX_FATOS]:
        if not isinstance(f, dict):
            continue
        texto = _texto(f.get("texto"), 250)
        if not texto:
            continue
        para = f.get("para")
        if para == "todos":
            fatos.append({"texto": texto, "todos": True, "personagens": []})
            continue
        ids = []
        for ref in _lista(para):
            if isinstance(ref, str):
                ident = ref.removeprefix("character:")
                if ident in ids_personagens and ident not in ids:
                    ids.append(ident)
        if ids:   # sem destinatário válido, o fato é descartado
            fatos.append({"texto": texto, "todos": False, "personagens": ids})

    return {"ganchos": ganchos, "npcs": npcs, "vinculos": vinculos, "fatos": fatos}