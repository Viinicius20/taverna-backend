from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from auth import MESTRE
from core import campanha_atual, supabase

router = APIRouter(prefix="/encontros-preparados", dependencies=MESTRE)


class InimigoIn(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    quantidade: int = Field(default=1, ge=1, le=20)
    hp: int | None = Field(default=None, ge=1, le=9999)
    dex: int | None = Field(default=None, ge=1, le=30)
    cr: str = Field(default="", max_length=20)


class EncontroIn(BaseModel):
    local_id: UUID | None = None
    titulo: str = Field(min_length=1, max_length=120)
    descricao: str = Field(default="", max_length=3000)
    diferencial: str = Field(default="", max_length=1500)
    recompensa: str = Field(default="", max_length=1500)
    ligacao_mundo: str = Field(default="", max_length=1500)
    inimigos: list[InimigoIn] = Field(default_factory=list, max_length=20)


def dados_encontro(body: EncontroIn, campanha: str) -> dict:
    dados = body.model_dump(mode="json")
    dados["titulo"] = body.titulo.strip()

    if not dados["titulo"]:
        raise HTTPException(400, "Dê um título ao encontro.")

    if dados["local_id"]:
        local = (
            supabase.table("locations").select("id")
            .eq("id", dados["local_id"]).eq("campaign_id", campanha)
            .limit(1).execute().data
        )
        if not local:
            raise HTTPException(400, "Escolha um local da campanha atual.")

    for inimigo in dados["inimigos"]:
        inimigo["nome"] = inimigo["nome"].strip()
        if not inimigo["nome"]:
            raise HTTPException(400, "Preencha o nome das criaturas.")

    return dados


@router.get("")
def listar_encontros(local_id: UUID | None = None):
    consulta = (
        supabase.table("encontros_preparados").select("id,titulo,local_id")
        .eq("campaign_id", campanha_atual())
    )
    if local_id:
        consulta = consulta.eq("local_id", str(local_id))
    return {"data": consulta.order("criado_em", desc=True).execute().data or []}


@router.get("/{encontro_id}")
def buscar_encontro(encontro_id: UUID):
    linhas = (
        supabase.table("encontros_preparados").select("*")
        .eq("campaign_id", campanha_atual()).eq("id", str(encontro_id))
        .limit(1).execute().data or []
    )
    if not linhas:
        raise HTTPException(404, "Encontro não encontrado.")
    return {"data": linhas[0]}


@router.post("")
def criar_encontro(body: EncontroIn):
    campanha = campanha_atual()
    linha = supabase.table("encontros_preparados").insert({
        **dados_encontro(body, campanha),
        "campaign_id": campanha,
    }).execute().data[0]
    return {"data": linha}


@router.patch("/{encontro_id}")
def editar_encontro(encontro_id: UUID, body: EncontroIn):
    campanha = campanha_atual()
    linhas = (
        supabase.table("encontros_preparados").update(dados_encontro(body, campanha))
        .eq("campaign_id", campanha).eq("id", str(encontro_id)).execute().data or []
    )
    if not linhas:
        raise HTTPException(404, "Encontro não encontrado.")
    return {"data": linhas[0]}