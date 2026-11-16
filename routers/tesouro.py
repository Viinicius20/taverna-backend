from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import exigir_mestre, usuario_atual
from core import supabase, campanha_atual
from moedas import MOEDAS, aplicar_delta

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


@router.get("")
def ver_tesouro(user: dict = Depends(usuario_atual)):
    camp = campanha_atual()
    try:
        itens = (supabase.table("tesouro").select("*").eq("campaign_id", camp)
                 .order("created_at", desc=True).execute().data or [])
        m = supabase.table("tesouro_moedas").select("*").eq("campaign_id", camp).limit(1).execute().data
    except Exception as e:
        print(f"ERRO TESOURO: {e}")
        raise HTTPException(500, "Erro ao buscar o tesouro")
    atual = m[0] if m else {}
    return {"success": True, "data": {
        "itens": itens,
        "moedas": {k: atual.get(k, 0) for k in MOEDAS},
    }}


# precisa vir ANTES de /{item_id}, senão "moedas" seria lido como um id
@router.patch("/moedas")
def ajustar_moedas(req: MoedasReq, user: dict = Depends(exigir_mestre)):
    camp = campanha_atual()
    try:
        m = supabase.table("tesouro_moedas").select("*").eq("campaign_id", camp).limit(1).execute().data
        novo = aplicar_delta(m[0] if m else {}, req.model_dump())
        supabase.table("tesouro_moedas").upsert(
            {"campaign_id": camp, **novo}, on_conflict="campaign_id").execute()
    except Exception as e:
        print(f"ERRO MOEDAS: {e}")
        raise HTTPException(500, "Erro ao ajustar as moedas")
    return {"success": True, "data": novo}


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


@router.patch("/{item_id}", dependencies=[Depends(exigir_mestre)])
def editar_item(item_id: str, req: ItemPatch):
    dados = req.model_dump(exclude_none=True)
    if not dados:
        raise HTTPException(400, "Nada para alterar")
    if "nome" in dados:
        dados["nome"] = dados["nome"].strip()
    try:
        r = (supabase.table("tesouro").update(dados)
             .eq("id", item_id).eq("campaign_id", campanha_atual()).execute().data)
    except Exception as e:
        print(f"ERRO EDITAR TESOURO: {e}")
        raise HTTPException(500, "Erro ao editar o item")
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