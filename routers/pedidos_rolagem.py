from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from postgrest.exceptions import APIError
from pydantic import BaseModel, Field

from auth import exigir_mestre, usuario_atual
from core import campanha_atual, limiter, supabase
from motor_dados import rolar

router = APIRouter(prefix="/pedidos-rolagem", tags=["pedidos-rolagem"])

PERICIAS = {
    "acrobatics": ("Acrobacia", "dex"),
    "animal_handling": ("Adestrar Animais", "wis"),
    "arcana": ("Arcanismo", "int"),
    "athletics": ("Atletismo", "str"),
    "deception": ("Enganação", "cha"),
    "history": ("História", "int"),
    "insight": ("Intuição", "wis"),
    "intimidation": ("Intimidação", "cha"),
    "investigation": ("Investigação", "int"),
    "medicine": ("Medicina", "wis"),
    "nature": ("Natureza", "int"),
    "perception": ("Percepção", "wis"),
    "performance": ("Atuação", "cha"),
    "persuasion": ("Persuasão", "cha"),
    "religion": ("Religião", "int"),
    "sleight_of_hand": ("Prestidigitação", "dex"),
    "stealth": ("Furtividade", "dex"),
    "survival": ("Sobrevivência", "wis"),
}

ATRIBUTOS = {
    "str": "Força", "dex": "Destreza", "con": "Constituição",
    "int": "Inteligência", "wis": "Sabedoria", "cha": "Carisma",
}

TESTES = {
    "pericia": PERICIAS,
    "salvaguarda": {
        chave: (f"Salvaguarda de {nome}", chave)
        for chave, nome in ATRIBUTOS.items()
    },
}

CAMPOS_PEDIDO = (
    "id,pedido_id,character_id,rotulo,contexto,modo,cd,"
    "cd_oculta,fechado,resultado,criado_em"
)


class PedidoIn(BaseModel):
    tipo: Literal["pericia", "salvaguarda"]
    chave: str = Field(max_length=40)
    personagens: list[UUID] = Field(min_length=1, max_length=50)
    contexto: str = Field(default="", max_length=200)
    modo: Literal["normal", "vantagem", "desvantagem"] = "normal"
    cd: int | None = Field(default=None, ge=1, le=99)
    cd_oculta: bool = True


def ficha_do_jogador(character_id, user):
    linhas = (
        supabase.table("characters").select("id,name,data")
        .eq("campaign_id", campanha_atual())
        .eq("id", str(character_id)).eq("user_id", user["sub"])
        .limit(1).execute().data or []
    )
    if not linhas:
        raise HTTPException(404, "Personagem não encontrado.")
    return linhas[0]


def inteiro(valor, padrao):
    try:
        return int(valor)
    except (TypeError, ValueError, OverflowError):
        return padrao


def bonus_do_teste(ficha, tipo, chave):
    _, atributo = TESTES[tipo][chave]
    valor_atributo = inteiro((ficha.get("attributes") or {}).get(atributo), 10)
    padrao = (valor_atributo - 10) // 2

    if tipo == "pericia":
        campos = ficha.get("skills") or {}
    else:
        campos = (ficha.get("combat") or {}).get("saving_throws") or {}

    return inteiro(campos.get(chave), padrao)


def dados_do_jogador(linha):
    return {
        "id": linha["id"],
        "rotulo": linha["rotulo"],
        "contexto": linha["contexto"],
        "modo": linha["modo"],
        "cd": None if linha["cd_oculta"] else linha["cd"],
        "resultado": linha["resultado"],
    }


@router.get("/opcoes", dependencies=[Depends(exigir_mestre)])
def opcoes():
    return {"data": {
        tipo: [{"chave": chave, "rotulo": nome} for chave, (nome, _) in itens.items()]
        for tipo, itens in TESTES.items()
    }}


@router.get("", dependencies=[Depends(exigir_mestre)])
def listar_pedidos():
    linhas = (
        supabase.table("pedidos_rolagem").select(CAMPOS_PEDIDO)
        .eq("campaign_id", campanha_atual()).eq("fechado", False)
        .order("criado_em", desc=True).execute().data or []
    )
    return {"data": linhas}


@router.post("")
def criar_pedido(body: PedidoIn, user: dict = Depends(exigir_mestre)):
    teste = TESTES[body.tipo].get(body.chave)
    if not teste:
        raise HTTPException(400, "Escolha um teste válido.")

    campanha = campanha_atual()
    ids = list(dict.fromkeys(str(p) for p in body.personagens))
    personagens = (
        supabase.table("characters").select("id,user_id")
        .eq("campaign_id", campanha).in_("id", ids).execute().data or []
    )
    if len(personagens) != len(ids) or any(not p.get("user_id") for p in personagens):
        raise HTTPException(400, "Escolha personagens com jogador nesta campanha.")

    pedido_id = str(uuid4())
    supabase.table("pedidos_rolagem").insert([
        {
            "pedido_id": pedido_id,
            "campaign_id": campanha,
            "character_id": personagem,
            "tipo": body.tipo,
            "chave": body.chave,
            "rotulo": teste[0],
            "contexto": body.contexto.strip(),
            "modo": body.modo,
            "cd": body.cd,
            "cd_oculta": body.cd_oculta,
        }
        for personagem in ids
    ]).execute()

    return {"data": {"pedido_id": pedido_id}}


@router.patch("/{pedido_id}/fechar", dependencies=[Depends(exigir_mestre)])
def fechar_pedido(pedido_id: UUID):
    supabase.table("pedidos_rolagem").update({"fechado": True}) \
        .eq("campaign_id", campanha_atual()).eq("pedido_id", str(pedido_id)).execute()
    return {"success": True}


@router.get("/personagem/{character_id}")
def pedidos_do_personagem(character_id: UUID, user: dict = Depends(usuario_atual)):
    ficha_do_jogador(character_id, user)

    linhas = (
        supabase.table("pedidos_rolagem").select(CAMPOS_PEDIDO)
        .eq("campaign_id", campanha_atual()).eq("character_id", str(character_id))
        .eq("fechado", False).order("criado_em", desc=True).execute().data or []
    )
    return {"data": [dados_do_jogador(linha) for linha in linhas]}


@router.post("/{linha_id}/responder")
@limiter.limit("60/minute")
def responder(request: Request, linha_id: UUID, user: dict = Depends(usuario_atual)):
    campanha = campanha_atual()
    linhas = (
        supabase.table("pedidos_rolagem")
        .select(f"{CAMPOS_PEDIDO},tipo,chave")
        .eq("campaign_id", campanha).eq("id", str(linha_id))
        .limit(1).execute().data or []
    )
    if not linhas:
        raise HTTPException(404, "Pedido não encontrado.")

    linha = linhas[0]
    personagem = ficha_do_jogador(linha["character_id"], user)
    if linha["resultado"] is not None:
        return {"data": dados_do_jogador(linha)}
    if linha["fechado"]:
        raise HTTPException(409, "O Mestre já fechou este pedido.")

    ficha = personagem.get("data") or {}
    bonus = bonus_do_teste(ficha, linha["tipo"], linha["chave"])
    if abs(bonus) > 999:
        raise HTTPException(400, "Confira o bônus salvo na ficha.")

    expressao = f"1d20{bonus:+d}" if bonus else "1d20"
    resultado = rolar(expressao, linha["modo"])

    try:
        linha["resultado"] = supabase.rpc("responder_pedido_rolagem", {
            "p_id": str(linha_id),
            "p_campanha": campanha,
            "p_jogador": user["sub"],
            "p_autor": (ficha.get("name") or personagem.get("name") or "Personagem")[:80],
            "p_resultado": resultado,
        }).execute().data
    except APIError as e:
        if e.code in {"PT404", "PT409"}:
            raise HTTPException(int(e.code[2:]), e.message) from e
        raise

    return {"data": dados_do_jogador(linha)}