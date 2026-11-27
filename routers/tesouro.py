from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Literal
from uuid import UUID
from auth import exigir_mestre, usuario_atual
from core import supabase, campanha_atual
from moedas import MOEDAS
from postgrest.exceptions import APIError

router = APIRouter(prefix="/tesouro", tags=["tesouro"])


class ItemReq(BaseModel):
    nome: str = Field(min_length=1, max_length=80)
    quantidade: int = Field(default=1, ge=0, le=9999)
    notas: Optional[str] = Field(default=None, max_length=300)
    valor_po: Optional[int] = Field(default=None, ge=0, le=10_000_000)


class ItemPatch(BaseModel):
    nome: Optional[str] = Field(default=None, min_length=1, max_length=80)
    quantidade: Optional[int] = Field(default=None, ge=0, le=9999)
    notas: Optional[str] = Field(default=None, max_length=300)
    valor_po: Optional[int] = Field(default=None, ge=0, le=10_000_000)


class MoedasReq(BaseModel):
    cobre: int = Field(default=0, ge=-1_000_000, le=1_000_000)
    prata: int = Field(default=0, ge=-1_000_000, le=1_000_000)
    electro: int = Field(default=0, ge=-1_000_000, le=1_000_000)
    ouro: int = Field(default=0, ge=-1_000_000, le=1_000_000)
    platina: int = Field(default=0, ge=-1_000_000, le=1_000_000)

class DivisaoReq(BaseModel):
    moeda: Literal["cobre", "prata", "electro", "ouro"]
    valor: int = Field(ge=1, le=10_000_000)
    personagens: list[UUID] = Field(min_length=1)
    operacao_id: UUID


class EntregaReq(BaseModel):
    item: UUID
    personagem: UUID
    quantidade: int = Field(ge=1, le=9999)
    operacao_id: UUID

class SaqueItemReq(BaseModel):
    nome: str = Field(min_length=1, max_length=80)
    quantidade: int = Field(default=1, ge=1, le=9999)
    notas: str | None = Field(default=None, max_length=300)


class SaqueMoedasReq(BaseModel):
    cobre: int = Field(default=0, ge=0, le=1_000_000)
    prata: int = Field(default=0, ge=0, le=1_000_000)
    electro: int = Field(default=0, ge=0, le=1_000_000)
    ouro: int = Field(default=0, ge=0, le=1_000_000)
    platina: int = Field(default=0, ge=0, le=1_000_000)


class SaqueReq(BaseModel):
    operacao_id: UUID
    origem: str = Field(min_length=1, max_length=160)
    itens: list[SaqueItemReq] = Field(default_factory=list, max_length=30)
    moedas: SaqueMoedasReq = Field(default_factory=SaqueMoedasReq)

@router.get("")
def ver_tesouro(user: dict = Depends(usuario_atual)):
    camp = campanha_atual()
    try:
        itens = (supabase.table("tesouro").select("*").eq("campaign_id", camp)
                 .order("created_at", desc=True).execute().data or [])
        m = supabase.table("tesouro_moedas").select("*").eq("campaign_id", camp).limit(1).execute().data
        historico = (
            supabase.table("tesouro_historico")
            .select("id,dia_total,descricao")
            .eq("campaign_id", camp)
            .order("criado_em", desc=True)
            .limit(100).execute().data or []
        )
    except Exception as e:
        print(f"ERRO TESOURO: {e}")
        raise HTTPException(500, "Erro ao buscar o tesouro")
    atual = m[0] if m else {}
    return {"success": True, "data": {
        "itens": itens,
        "moedas": {k: atual.get(k, 0) for k in MOEDAS},
        "historico": historico,
    }}

def movimentar(acao, dados, operacao=None):
    try:
        return supabase.rpc("tesouro_movimentar", {
            "p_campanha": campanha_atual(),
            "p_acao": acao,
            "p_dados": dados,
            "p_operacao": str(operacao) if operacao else None,
        }).execute().data
    except APIError as e:
        if e.code in {"PT400", "PT404", "PT409"}:
            raise HTTPException(int(e.code[2:]), e.message) from e
        raise HTTPException(500, "Erro ao movimentar o tesouro.") from e


@router.patch("/moedas")
def ajustar_moedas(req: MoedasReq, user: dict = Depends(exigir_mestre)):
    return {"success": True, "data": movimentar("ajustar", req.model_dump())}


@router.post("/dividir", dependencies=[Depends(exigir_mestre)])
def dividir_moedas(req: DivisaoReq):
    dados = req.model_dump(mode="json", exclude={"operacao_id"})
    return movimentar("dividir", dados, req.operacao_id)


@router.post("/entregar", dependencies=[Depends(exigir_mestre)])
def entregar_item(req: EntregaReq):
    dados = req.model_dump(mode="json", exclude={"operacao_id"})
    return movimentar("entregar", dados, req.operacao_id)


@router.post("")
def adicionar_item(req: ItemReq, user: dict = Depends(exigir_mestre)):
    try:
        linha = supabase.table("tesouro").insert({
            "campaign_id": campanha_atual(),
            "nome": req.nome.strip(),
            "quantidade": req.quantidade,
            "notas": (req.notas or "").strip() or None,
            "valor_po": req.valor_po,
            "adicionado_por": user["sub"],
        }).execute().data[0]
    except Exception as e:
        print(f"ERRO ADICIONAR TESOURO: {e}")
        raise HTTPException(500, "Erro ao adicionar o item")
    return {"success": True, "data": linha}

@router.post("/saque")
def receber_saque(req: SaqueReq, user: dict = Depends(exigir_mestre)):
    origem = req.origem.strip()
    itens = [
        {
            "nome": item.nome.strip(),
            "quantidade": item.quantidade,
            "notas": (item.notas or "").strip() or None,
        }
        for item in req.itens
    ]
    moedas = req.moedas.model_dump()

    if not origem or any(not item["nome"] for item in itens):
        raise HTTPException(400, "Preencha a origem e o nome dos itens.")
    if not itens and not any(moedas.values()):
        raise HTTPException(400, "Inclua itens ou moedas no saque.")

    try:
        return supabase.rpc("tesouro_receber_saque", {
            "p_campanha": campanha_atual(),
            "p_mestre": user["sub"],
            "p_operacao": str(req.operacao_id),
            "p_origem": origem,
            "p_itens": itens,
            "p_moedas": moedas,
        }).execute().data
    except APIError as e:
        if e.code == "PT400":
            raise HTTPException(400, e.message) from e
        raise HTTPException(500, "Não foi possível enviar o saque ao Tesouro.") from e

@router.patch("/{item_id}", dependencies=[Depends(exigir_mestre)])
def editar_item(item_id: str, req: ItemPatch, quantidade_anterior: Optional[int] = None):
    dados = req.model_dump(exclude_none=True)
    if not dados:
        raise HTTPException(400, "Nada para alterar")
    if "nome" in dados:
        dados["nome"] = dados["nome"].strip()
    try:
        consulta = (
            supabase.table("tesouro").update(dados)
            .eq("id", item_id).eq("campaign_id", campanha_atual())
        )
        if quantidade_anterior is not None:
            consulta = consulta.eq("quantidade", quantidade_anterior)
        r = consulta.execute().data
    except Exception as e:
        print(f"ERRO EDITAR TESOURO: {e}")
        raise HTTPException(500, "Erro ao editar o item")
    if not r and quantidade_anterior is not None:
        raise HTTPException(409, "A quantidade mudou. Confira o tesouro atualizado.")
    if not r:
        raise HTTPException(404, "Item não encontrado")
    return {"success": True, "data": r[0]}


@router.delete("/{item_id}", dependencies=[Depends(exigir_mestre)])
def remover_item(item_id: str):
    try:
        r = (supabase.table("tesouro").delete()
             .eq("id", item_id).eq("campaign_id", campanha_atual()).execute().data)
    except Exception as e:
        print(f"ERRO REMOVER TESOURO: {e}")
        raise HTTPException(500, "Erro ao remover o item")
    if not r:
        raise HTTPException(404, "Item não encontrado")
    return {"success": True}