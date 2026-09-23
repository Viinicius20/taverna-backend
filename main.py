import os
import json
import uuid
import time
import fitz
import random
import string
import base64
import tempfile
import urllib.parse
import math
import random
from google.genai.errors import ServerError
from fastapi import FastAPI, HTTPException, UploadFile, File, Request, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import Optional
from pydantic import BaseModel
from supabase import create_client, Client
from dotenv import load_dotenv
from google import genai
from google.genai import types
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import FastAPI, HTTPException, UploadFile, File, Request, Body, Form
from pywebpush import webpush, WebPushException
from datetime import datetime

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

VELOCIDADE_KM_DIA = 40
CHANCE_EVENTO_POR_DIA = 0.35

VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY")
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY")
VAPID_CLAIMS = {"sub": "mailto:viniciusamoury0403@gmail.com"}

from cryptography.hazmat.primitives.serialization import load_pem_private_key

def get_vapid_private_key_object():
    key = VAPID_PRIVATE_KEY
    if not key:
        return None
    pem = key.replace('\\n', '\n').encode('utf-8')
    return load_pem_private_key(pem, password=None)

load_dotenv()

# ===================== CONFIG =====================
app = FastAPI(title="RPG IA - Backend")

ARQUETIPOS_POR_CLASSE = {
    "Guerreiro": {"nivel": 3, "arquetipos": ["Campeão", "Cavaleiro Arcano", "Mestre de Batalha", "Cavaleiro Eldritch", "Samurai", "Lutador", "Cavaleiro Rúnico", "Guerreiro Psíquico"]},
    "Fighter": {"nivel": 3, "arquetipos": ["Champion", "Arcane Archer", "Battle Master", "Eldritch Knight", "Samurai", "Psi Warrior", "Rune Knight", "Cavalier"]},

    "Monge": {"nivel": 3, "arquetipos": ["Guerreiro da Mão Aberta", "Sombra", "Elemento", "Alma do Sol", "Punho Bêbado", "Kensei"]},
    "Monk": {"nivel": 3, "arquetipos": ["Open Hand", "Shadow", "Four Elements", "Sun Soul", "Drunken Master", "Kensei"]},

    "Ladino": {"nivel": 3, "arquetipos": ["Trapaceiro Arcano", "Assassino", "Ladrão", "Swashbuckler", "Inquisidor", "Fantasma", "Espadachim da Alma"]},
    "Rogue": {"nivel": 3, "arquetipos": ["Arcane Trickster", "Assassin", "Thief", "Swashbuckler", "Inquisitive", "Phantom", "Soulknife"]},

    "Mago": {"nivel": 2, "arquetipos": ["Evocação", "Abjuração", "Ilusão", "Necromancia", "Adivinhação", "Transmutação", "Encantamento", "Conjuração", "Ordem dos Escribas", "Cantor de Espadas"]},
    "Wizard": {"nivel": 2, "arquetipos": ["Evocation", "Abjuration", "Illusion", "Necromancy", "Divination", "Transmutation", "Enchantment", "Conjuration", "Order of Scribes", "Bladesinging"]},

    "Clérigo": {"nivel": 1, "arquetipos": ["Vida", "Luz", "Conhecimento", "Guerra", "Natureza", "Tempestade", "Enganação", "Morte", "Paz", "Crepúsculo"]},
    "Cleric": {"nivel": 1, "arquetipos": ["Life", "Light", "Knowledge", "War", "Nature", "Tempest", "Trickery", "Death", "Peace", "Twilight"]},

    "Bardo": {"nivel": 3, "arquetipos": ["Colégio do Saber", "Colégio do Valor", "Colégio da Criação", "Colégio da Eloquência", "Colégio dos Sussurros"]},
    "Bard": {"nivel": 3, "arquetipos": ["College of Lore", "College of Valor", "College of Creation", "College of Eloquence", "College of Whispers"]},

    "Bruxo": {"nivel": 1, "arquetipos": ["Arquifada", "Ancião", "Diabo", "Gólem", "Celestial", "Lâmina Amaldiçoada"]},
    "Warlock": {"nivel": 1, "arquetipos": ["Archfey", "Great Old One", "Fiend", "Hexblade", "Celestial", "Undying"]},

    "Paladino": {"nivel": 3, "arquetipos": ["Devoção", "Vingança", "Ancestral", "Glória", "Conquista", "Redenção"]},
    "Paladin": {"nivel": 3, "arquetipos": ["Devotion", "Vengeance", "Ancients", "Glory", "Conquest", "Redemption"]},

    "Druida": {"nivel": 2, "arquetipos": ["Círculo da Lua", "Círculo da Terra", "Círculo dos Sonhos", "Círculo do Pastor", "Círculo das Estrelas"]},
    "Druid": {"nivel": 2, "arquetipos": ["Circle of the Moon", "Circle of the Land", "Circle of Dreams", "Circle of the Shepherd", "Circle of Stars"]},

    "Patrulheiro": {"nivel": 3, "arquetipos": ["Caçador", "Mestre das Bestas", "Deslizador Horizonte", "Andarilho Feérico", "Enxameador"]},
    "Ranger": {"nivel": 3, "arquetipos": ["Hunter", "Beast Master", "Gloom Stalker", "Fey Wanderer", "Swarmkeeper"]},

    "Feiticeiro": {"nivel": 1, "arquetipos": ["Origem Dracônica", "Magia Selvagem", "Alma Divina", "Sombra", "Mente Aberrante", "Alma Mecânica"]},
    "Sorcerer": {"nivel": 1, "arquetipos": ["Draconic Bloodline", "Wild Magic", "Divine Soul", "Shadow Magic", "Aberrant Mind", "Clockwork Soul"]},

    "Bárbaro": {"nivel": 3, "arquetipos": ["Berserker", "Totem", "Zealot", "Storm Herald", "Magia Selvagem", "Fera Ancestral"]},
    "Barbarian": {"nivel": 3, "arquetipos": ["Berserker", "Totem Warrior", "Zealot", "Storm Herald", "Wild Magic", "Beast"]},
}

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request, exc):
    return JSONResponse(status_code=429, content={"detail": "Muitas requisições. Tente novamente em alguns segundos."})

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://taverna-frontend.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

supabase: Client = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")
)

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


# ===================== MODELOS =====================
class CreateCharacterRequest(BaseModel):
    description: str
    system: str = "D&D 5e"
    campaign_context: str = ""
    user_id: str = ""
    campaign_id: str = ""

class UpdateCharacterRequest(BaseModel):
    data: dict
    name: str = ""
    system: str = ""

class LevelUpRequest(BaseModel):
    character_id: str
    ficha_atual: dict
    nivel_alvo: int
    system: str = "D&D 5e"
    class_name: Optional[str] = None
    arquetipo: Optional[str] = None

class HombrewSpellRequest(BaseModel):
    name: str
    class_name: str

class AsiRequest(BaseModel):
    character_id: str
    ficha_atual: dict
    class_name: str
    nivel_alvo: int
    tipo: str  # "atributos" | "feat"
    alocacao: Optional[dict] = None      # ex: {"str": 1, "dex": 1}
    feat_nome: Optional[str] = None
    feat_descricao: Optional[str] = None

class GerarArteRequest(BaseModel):
    tipo: str  # "npc" | "item"
    id: str
    descricao_customizada: str = ""

class DeletarArteRequest(BaseModel):
    tipo: str
    id: str

class EncerrarSessaoRequest(BaseModel):
    campaign_id: str
    title: str = ""

# ===================== FUNÇÃO AUXILIAR GEMINI =====================
from google.genai.errors import ServerError
import time

GEMINI_KEYS = [
    os.getenv("GEMINI_API_KEY"),
    os.getenv("GEMINI_API_KEY_3"),
    os.getenv("GEMINI_API_KEY_2"),
    os.getenv("GEMINI_API_KEY_4"),
]

CAMPANHA_ID = "00000000-0000-0000-0000-000000000001"

def gerar_json_com_gemini(prompt: str, max_retries=3) -> dict:
    last_error = None

    for key in GEMINI_KEYS:
        if not key:
            continue
        client_atual = genai.Client(api_key=key)

        for tentativa in range(max_retries):
            try:
                response = client_atual.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.7,
                        response_mime_type="application/json"
                    )
                )
                text = response.text.strip()
                if text.startswith("```json"):
                    text = text[7:-3].strip()
                return json.loads(text)

            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    print(f"[IA] Quota esgotada na key, tentando próxima...")
                    last_error = e
                    break  # vai pra próxima key
                elif "503" in err_str or "UNAVAILABLE" in err_str:
                    last_error = e
                    print(f"[IA] 503 tentativa {tentativa+1}/{max_retries}")
                    time.sleep(2 * (tentativa + 1))
                else:
                    last_error = e
                    break

    raise last_error


# ===================== ENDPOINTS =====================

@app.post("/create-character")
@limiter.limit("10/minute")
async def create_character(request: Request, req: CreateCharacterRequest):
    prompt = f"""
    Você é um mestre experiente de RPG. Crie uma ficha completa e equilibrada.

    Sistema: {req.system}
    Descrição do jogador: {req.description}
    Contexto da campanha: {req.campaign_context or 'Nenhum'}

    **OBRIGATÓRIO**: Sempre inclua o objeto "combat" com todos os campos abaixo calculados corretamente:
    - hp e hp_max (baseado na classe + modificador de CON)
    - ac (Classe de Armadura)
    - initiative
    - speed
    - proficiency_bonus
    - passive_perception
    - hit_dice
    - saving_throws (para os 6 atributos)
    
    **CRÍTICO**: Retorne APENAS um JSON válido e COMPLETO. Nenhum JSON incompleto ou truncado. Feche TODOS os arrays e objetos corretamente com }} e ].

    **IMPORTANTE - CLASSES**: Se a descrição mencionar múltiplas classes (ex: "Guerreiro que virou Bruxo"), 
    retorne "classes" como um ARRAY com nome + level individual. 
    HP deve ser a SOMA dos hit dice de ambas as classes + bônus CON.

    Retorne APENAS um JSON válido com esta estrutura exata:
    {{
      "name": "Nome",
      "race": "...",
      "classes": [
            {{"name": "Guerreiro", "level": 5}},
            {{"name": "Bruxo", "level": 1}}
        ],
      "subclass": "Mestre de Batalha",
      "level": 1,
      "alignment": "...",
      "background": "...",
      "attributes": {{ "str": 10, "dex": 15, "con": 14, "int": 8, "wis": 16, "cha": 8 }},
      "combat": {{
        "hp": 0,
        "hp_max": 0,
        "ac": 0,
        "initiative": 0,
        "speed": 30,
        "proficiency_bonus": 2,
        "passive_perception": 0,
        "hit_dice": "1d8",
        "saving_throws": {{ "str": 0, "dex": 0, "con": 0, "int": 0, "wis": 0, "cha": 0 }}
      }},
      "spellcasting": {{
        "ability": "int",
        "dc": 15,
        "spells": []
        **Spellcasting deve ter spells sempre como array vazio []. Não preencha com nada.**
      }},
      "skills": {{ "acrobatics": 5, "stealth": 3, ... }},
      "inventory": ["item1", "item2"],
      "features": ["feature1", "feature2"],
      "background_story": "História curta..."
    }}
    """
    try:
        print(f"DEBUG 1: Enviando prompt para IA...")
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[{"role": "user", "parts": [{"text": prompt}]}]
        )
        raw = response.text.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        ficha = json.loads(raw)
        print(f"DEBUG 2: IA respondeu: {ficha}")


        # Validar e converter classes
        if isinstance(ficha.get("class"), str):
            classes_str = ficha.get("class", "")
            if " / " in classes_str or " e " in classes_str.lower():
                class_names = [c.strip() for c in classes_str.replace(" e ", " / ").split(" / ")]
                ficha["classes"] = [{"name": name, "level": 1} for name in class_names]
            else:
                ficha["classes"] = [{"name": classes_str, "level": 1}]
            ficha.pop("class", None)
        else:
            ficha["classes"] = ficha.get("classes", [{"name": "Guerreiro", "level": 1}])

        # Calcular total_level
        total_level = sum(c.get("level", 1) for c in ficha.get("classes", []))
        ficha["total_level"] = total_level
        if not ficha.get("arquetipo") and ficha.get("subclass"):
            ficha["arquetipo"] = ficha["subclass"]
        ficha.pop("class", None)

        insert_data = {
            "name": ficha.get("name", "Sem nome"),
            "system": req.system,
            "data": ficha,
        }
        if req.user_id:
            insert_data["user_id"] = req.user_id
        if req.campaign_id:
            insert_data["campaign_id"] = req.campaign_id

        response = supabase.table("characters").insert(insert_data).execute()

        return {
            "success": True,
            "data": ficha,
            "saved_id": response.data[0]["id"] if response.data else None
        }
    except ServerError:
        raise HTTPException(
            status_code=503,
            detail="IA sobrecarregada, tente novamente em alguns segundos"
        )

    except json.JSONDecodeError:
        raise HTTPException(
            status_code=502,
            detail="Erro ao interpretar resposta da IA"
        )

    except Exception as e:
        print(f"ERRO GERAL: {str(e)}")
        raise HTTPException(500, "Erro ao processar PDF")


@app.put("/characters/{character_id}")
async def update_character(character_id: str, req: UpdateCharacterRequest):
    try:
        print(f"SALVANDO: ataques={req.data.get('ataques')}, notas={req.data.get('notas_privadas')}")
        update_data = {"data": req.data}
        if req.name:
            update_data["name"] = req.name
        if req.system:
            update_data["system"] = req.system
        response = supabase.table("characters").update(update_data).eq("id", character_id).execute()
        return {"success": True, "data": response.data}
    except Exception as e:
        raise HTTPException(500, f"Erro ao atualizar personagem: {str(e)}")

class LootRequest(BaseModel):
    nivel_medio: int = 5
    quantidade_mundanos: int = 4
    quantidade_magicos: int = 1
    contexto: str = ""

@app.post("/loot/generate")
async def generate_loot(req: LootRequest):
    prompt = f"""Você é um mestre de D&D 5e experiente.
Gere uma lista de itens de loot para um grupo de nível {req.nivel_medio}.
Contexto: {req.contexto or 'inimigos genéricos derrotados'}

Retorne APENAS um JSON válido neste formato exato:
{{
  "mundanos": ["item1", "item2", "item3", "item4"],
  "magicos": [
    {{
      "nome": "Nome do Item",
      "raridade": "Comum/Incomum/Raro/Muito Raro/Lendário",
      "descricao": "Descrição curta do item e seus efeitos mágicos"
    }}
  ]
}}

{req.quantidade_mundanos} itens mundanos e {req.quantidade_magicos} item(ns) mágico(s).
Itens mundanos: moedas, poções simples, comida, equipamentos comuns.
Itens mágicos: apropriados pro nível {req.nivel_medio}, criativos e únicos."""

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        raw = response.text.strip().replace("```json", "").replace("```", "").strip()
        loot = json.loads(raw)
        return {"success": True, "data": loot}
    except json.JSONDecodeError:
        raise HTTPException(400, {"error": "IA não retornou JSON válido"})
    except Exception as e:
        print(f"ERRO LOOT: {e}")
        raise HTTPException(500, {"error": f"Erro ao gerar loot: {str(e)}"})

def gerar_texto_com_gemini(parts_ou_prompt, max_retries=3):
    """Aceita string simples (prompt) ou lista de parts (multimodal, ex: PDF com imagens)."""
    last_error = None
    contents = parts_ou_prompt if isinstance(parts_ou_prompt, list) else parts_ou_prompt

    for idx, key in enumerate(GEMINI_KEYS):
        if not key:
            continue
        client_atual = genai.Client(api_key=key)

        for tentativa in range(max_retries):
            try:
                if isinstance(parts_ou_prompt, list):
                    response = client_atual.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=[{"role": "user", "parts": parts_ou_prompt}]
                    )
                else:
                    response = client_atual.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=parts_ou_prompt,
                        config=types.GenerateContentConfig(
                            temperature=0.7,
                            response_mime_type="application/json"
                        )
                    )
                return response.text.strip()

            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    print(f"[IA] Key {idx+1}: quota esgotada, indo pra próxima key...")
                    last_error = e
                    break
                elif "503" in err_str or "UNAVAILABLE" in err_str:
                    last_error = e
                    print(f"[IA] Key {idx+1}: 503 (tentativa {tentativa+1}/{max_retries})")
                    time.sleep(2 * (tentativa + 1))
                else:
                    last_error = e
                    print(f"[IA] Key {idx+1}: erro não tratado — {err_str[:200]}")
                    break

    raise last_error


@app.post("/level-up")
@limiter.limit("10/minute")
async def level_up(request: Request, req: LevelUpRequest):
    ficha = req.ficha_atual
    nivel_atual = ficha.get("level", 1)

    if req.nivel_alvo <= nivel_atual:
        raise HTTPException(400, "Nível alvo deve ser maior que o nível atual")
    if req.nivel_alvo > 20:
        raise HTTPException(400, "Nível máximo é 20")

    # ← fora dos ifs agora
    class_name_alvo = getattr(req, 'class_name', None)

    if isinstance(ficha.get("classes"), list) and len(ficha["classes"]) > 1:
        if not class_name_alvo:
            raise HTTPException(400, {
                "error": "Escolha qual classe fazer level up",
                "classes": [{"name": c["name"], "level": c["level"]} for c in ficha["classes"]]
            })
        classe_encontrada = next(
            (c for c in ficha["classes"] if c["name"].lower() == class_name_alvo.lower()), None
        )
        if not classe_encontrada:
            raise HTTPException(400, f"Classe '{class_name_alvo}' não encontrada")
        classe_encontrada["level"] += 1
        ficha["total_level"] = sum(c.get("level", 1) for c in ficha["classes"])
    else:
        if isinstance(ficha.get("classes"), list) and len(ficha["classes"]) == 1:
            ficha["classes"][0]["level"] += 1
            ficha["total_level"] = ficha["classes"][0]["level"]

    # Atualiza o level na ficha antes de mandar pra IA
    ficha["level"] = req.nivel_alvo

    arquetipo_txt = f"\nArquétipo escolhido AGORA para a classe {class_name_alvo}: {req.arquetipo} — adicione todas as features deste arquétipo." if req.arquetipo else f"\nArquétipo atual: {ficha.get('arquetipo', 'nenhum')}"

    prompt = f"""
    Você é um mestre experiente de RPG. Um personagem subiu de nível.

    Sistema: {req.system}
    Nome: {ficha.get("name")}
    Raça: {ficha.get("race")}
    Classes: {json.dumps(ficha.get("classes", [{"name": ficha.get("class")}]))}
    Nível atual: {nivel_atual}
    Nível alvo: {req.nivel_alvo}
    {arquetipo_txt}
    Features atuais: {json.dumps(ficha.get("features", []))}
    Atributos atuais: {json.dumps(ficha.get("atributos", ficha.get("attributes", {})))}
    Combat atual: {json.dumps(ficha.get("combat", {}))}

    Atualize a ficha para o nível {req.nivel_alvo}. Retorne APENAS um JSON válido com
    a ficha COMPLETA atualizada, usando EXATAMENTE os mesmos nomes de campo da ficha original.
    Não traduza nem renomeie campos. Preserve todos os campos que não precisam mudar.

    Campos que DEVEM ser recalculados para o nível {req.nivel_alvo}:
    - level: {req.nivel_alvo}
    - combat.hp_max: recalcule com a Hit Die da classe + modificador de CON por nível
    - combat.hp: igual ao hp_max novo (full heal no level up)
    - combat.proficiency (ou proficiency_bonus): recalcule pela tabela padrão de D&D 5e
    - combat.saving_throws: recalcule com o novo bônus de proficiência
    - features: adicione TODAS as novas features/habilidades do nível {req.nivel_alvo}, no formato: 
    [{{"nome": "Nome da Feature", "origem": "classe"}}, ...]. 
    Use "origem": "racial" para features de raça (incluindo traços de subrraças e linhagens como Tabaxi, Tiefling, Dragonborn, etc — 
    ex: Darkvision, Feline Agility, Cat's Claws, Breath Weapon, Fire Resistance, Flight, Innate Spellcasting, Natural Armor, Powerful Build), 
    "antecedente" para features de background, "classe" para o resto.
    - Se houver Ability Score Improvement neste nível, aplique nos atributos

    Campos que DEVEM ser preservados exatamente como estão:
    - name: {ficha.get("name")}
    - race: {ficha.get("race")}
    - background: {ficha.get("background")}
    - alignment: {ficha.get("alignment")}
    - classes: preserve o array de classes
    - skills: preserve as perícias existentes (apenas atualize bônus de proficiência)
    - inventory: preserve exatamente
    - background_story: preserve exatamente
    - xp: preserve exatamente
    - arquetipo: NÃO preencha este campo com texto descritivo. Deixe null/vazio se o personagem ainda não escolheu um arquétipo/subclasse.

    Retorne a ficha com a mesma estrutura recebida, apenas com os campos acima atualizados.
    """

    try:
        ficha_nova = gerar_json_com_gemini(prompt)

        # Preservar campos que a IA pode ignorar
        campos_preservar = [
    "background", "alignment", "background_story", "inventory", "xp", "classes", "name", "race",
    "ideais", "vinculos", "defeitos", "objetivo_atual", "medos", "languages", "appearance"
]
        for campo in campos_preservar:
            if campo in ficha and (campo not in ficha_nova or not ficha_nova[campo]):
                ficha_nova[campo] = ficha[campo]

        # Preservar arquetipos já resolvidos de outras classes antes de aplicar o novo
        if isinstance(ficha.get("arquetipos"), dict):
            ficha_nova["arquetipos"] = {**ficha["arquetipos"], **ficha_nova.get("arquetipos", {})}

        if req.arquetipo:
            if class_name_alvo:
                if "arquetipos" not in ficha_nova or not isinstance(ficha_nova.get("arquetipos"), dict):
                    ficha_nova["arquetipos"] = dict(ficha.get("arquetipos", {}))
                ficha_nova["arquetipos"][class_name_alvo] = req.arquetipo
            else:
                ficha_nova["arquetipo"] = req.arquetipo
        supabase.table("characters").update({
            "data": ficha_nova,
            "name": ficha_nova.get("name", ficha.get("name"))
        }).eq("id", req.character_id).execute()
        return {"success": True, "data": ficha_nova}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, "Erro ao processar level up")


@app.post("/upload-pdf")
@limiter.limit("5/minute")
async def upload_pdf(request: Request, file: UploadFile = File(...), system: str = "D&D 5e", user_id: str = "", campaign_id: str = ""):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Arquivo deve ser PDF")

    contents = await file.read()
    if not contents:
        raise HTTPException(400, "PDF está vazio ou corrompido")

    # Converte PDF para imagens
    try:
        import fitz
        import base64
        pdf_doc = fitz.open(stream=contents, filetype="pdf")
        parts = [{"text": f"""Extraia TODOS os dados da ficha de RPG das imagens abaixo.
Sistema: {system}

Retorne APENAS um JSON com esta estrutura exata:

IMPORTANTE: inventory deve ser array de STRINGS simples, nunca objetos.
IMPORTANTE: inventory deve ser array de STRINGS simples, nunca objetos.
IMPORTANTE: "alignment" deve ser APENAS o alinhamento moral (ex: Leal Bom, Caótico Neutro, Neutro). NÃO coloque arquétipo ou subclasse aqui.
IMPORTANTE: "background" deve ser o antecedente do personagem (ex: Haunted One, Sage, Criminal).
IMPORTANTE: "skills" deve conter TODAS as 18 perícias do D&D 5e, mesmo as não-proficientes. Use o modificador correto de cada uma (modificador do atributo base ± bônus de proficiência/expertise).
{{
  "name": "...",
  "race": "...",
  "class": "...",
  "level": 5,
  "alignment": "...",
  "background": "...",
  "classes": [{{"name": "Monk", "level": 4}}, {{"name": "Rogue", "level": 1}}],
  "attributes": {{"str": 10, "dex": 18, "con": 14, "int": 8, "wis": 16, "cha": 8}},
  "combat": {{
    "hp": 38, "hp_max": 38, "ac": 17, "initiative": 4, "speed": 40,
    "proficiency_bonus": 3, "passive_perception": 16,
    "saving_throws": {{"str": 3, "dex": 7, "con": 2, "int": -1, "wis": 3, "cha": -1}},
    "hit_dice": "4d8+1d8"
  }},
  "skills": {{
  "acrobatics": 7, "animal_handling": 3, "arcana": -1, "athletics": 6,
  "deception": -1, "history": -1, "insight": 6, "intimidation": -1,
  "investigation": 2, "medicine": 3, "nature": -1, "perception": 6,
  "performance": -1, "persuasion": -1, "religion": 2, "sleight_of_hand": 4,
  "stealth": 10, "survival": 3
}},
  "inventory": ["item 1 (qtd, peso)", "item 2 (qtd, peso)"],
  "features": [],
  "spellcasting": {{"ability": "", "dc": 0, "spells": []}},
  "background_story": ""
}}

Se tiver múltiplas classes, preencha o array "classes" com cada uma e seu nível.
Retorne APENAS o JSON, sem explicações.
"""}]
        for page in pdf_doc:
            pix = page.get_pixmap(dpi=150)
            img_bytes = pix.tobytes("png")
            parts.append({
                "inline_data": {
                    "mime_type": "image/png",
                    "data": base64.b64encode(img_bytes).decode()
                }
            })
        pdf_doc.close()
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Erro ao converter PDF: {str(e)}")

    # Chama Gemini com visão
    try:
        import json
        raw = gerar_texto_com_gemini(parts)
        raw = raw.replace("```json", "").replace("```", "").strip()
        ficha = json.loads(raw)

        insert_data = {
            "name": ficha.get("name", "Personagem importado"),
            "system": system,
            "data": ficha,
        }
        if user_id:
            insert_data["user_id"] = user_id
        if campaign_id:
            insert_data["campaign_id"] = campaign_id

        response = supabase.table("characters").insert(insert_data).execute()
        return {
            "success": True,
            "system": system,
            "data": ficha,
            "saved_id": response.data[0]["id"] if response.data else None,
            "message": "Ficha extraída e salva com sucesso!"
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Erro ao processar PDF: {str(e)}")


@app.post("/upload-pdf-npc")
async def upload_pdf_npc(file: UploadFile = File(...), system: str = "D&D 5e", campaign_id: str = ""):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Arquivo deve ser PDF")

    contents = await file.read()
    if not contents:
        raise HTTPException(400, "PDF está vazio ou corrompido")

    # Converte PDF para imagens
    try:
        import fitz
        import base64
        pdf_doc = fitz.open(stream=contents, filetype="pdf")
        parts = [{"text": f"""Extraia TODOS os dados da ficha de RPG das imagens e organize como NPC.
Sistema: {system}

Retorne APENAS um JSON com esta estrutura exata:
{{
  "name": "...",
  "race": "...",
  "class": "...",
  "level": 1,
  "alignment": "...",
  "background": "...",
  "occupation": "...",
  "personality": "...",
  "motivation": "...",
  "appearance": "...",
  "attributes": {{"str": 10, "dex": 18, "con": 14, "int": 8, "wis": 16, "cha": 8}},
  "combat": {{
    "hp": 0, "hp_max": 0, "ac": 0, "initiative": 0, "speed": 30,
    "proficiency_bonus": 2, "passive_perception": 0, "hit_dice": "1d8",
    "saving_throws": {{"str": 0, "dex": 0, "con": 0, "int": 0, "wis": 0, "cha": 0}}
  }},
  "features": [],
  "inventory": [],
  "secret_notes": ""
}}
Retorne APENAS o JSON, sem explicações.
"""}]
        for page in pdf_doc:
            pix = page.get_pixmap(dpi=150)
            img_bytes = pix.tobytes("png")
            parts.append({
                "inline_data": {
                    "mime_type": "image/png",
                    "data": base64.b64encode(img_bytes).decode()
                }
            })
        pdf_doc.close()
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Erro ao converter PDF: {str(e)}")

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[{"role": "user", "parts": parts}]
        )
        raw = response.text.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        dados = json.loads(raw)

        response = supabase.table("npcs").insert({
            "campaign_id": campaign_id,
            "name": dados.get("name", "NPC importado"),
            "data": dados
        }).execute()

        return {
            "success": True,
            "data": dados,
            "saved_id": response.data[0]["id"] if response.data else None,
            "message": "NPC importado com sucesso!"
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Erro ao processar NPC: {str(e)}")

@app.get("/characters")
async def list_characters(user_id: str = "", campaign_id: str = "", sem_dono: bool = False):
    try:
        query = supabase.table("characters").select("*")
        if user_id:
            query = query.eq("user_id", user_id)
        if campaign_id:
            query = query.eq("campaign_id", campaign_id)
        if sem_dono:
            query = query.is_("user_id", "null")
        response = query.order("created_at", desc=True).execute()
        return {"success": True, "data": response.data}
    except Exception as e:
        raise HTTPException(500, f"Erro ao buscar personagens: {str(e)}")


@app.get("/characters/{character_id}")
async def get_character(character_id: str):
    try:
        response = supabase.table("characters").select("*").eq("id", character_id).single().execute()
        if not response.data:
            raise HTTPException(404, "Personagem não encontrado")
        return {"success": True, "data": response.data}
    except Exception as e:
        raise HTTPException(500, f"Erro ao buscar personagem: {str(e)}")


@app.delete("/characters/{character_id}")
async def delete_character(character_id: str):
    try:
        supabase.table("characters").delete().eq("id", character_id).execute()
        return {"success": True, "message": "Personagem deletado"}
    except Exception as e:
        raise HTTPException(500, f"Erro ao deletar personagem: {str(e)}")

print("DEBUG: Endpoint /npcs foi chamado!")

@app.post("/npcs")
async def create_npc(campaign_id: str, description: str, system: str = "D&D 5e"):
    print(f"DEBUG: START create_npc")
    prompt = f"""
    Você é um mestre experiente de RPG. Crie um NPC interessante e detalhado.

    Sistema: {system}
    Descrição: {description}

    **OBRIGATÓRIO**: Sempre inclua o objeto "combat" com todos os campos abaixo calculados corretamente:
    - hp e hp_max (baseado na classe + modificador de CON)
    - ac (Classe de Armadura)
    - initiative
    - speed
    - proficiency_bonus
    - passive_perception
    - hit_dice
    - saving_throws (para os 6 atributos)

    Retorne APENAS um JSON válido:
    {{
      "name": "...",
      "race": "...",
      "occupation": "...",
      "personality": "...",
      "appearance": "...",
      "motivation": "...",
      "attributes": {{ "str": 10, "dex": 10, "con": 10, "int": 10, "wis": 10, "cha": 10 }},
      "combat": {{
        "hp": 0,
        "hp_max": 0,
        "ac": 0,
        "initiative": 0,
        "speed": 30,
        "proficiency_bonus": 2,
        "passive_perception": 0,
        "hit_dice": "1d8",
        "saving_throws": {{ "str": 0, "dex": 0, "con": 0, "int": 0, "wis": 0, "cha": 0 }}
      }},
      "features": [],
      "inventory": [],
      "background_story": "..."
    }}
    """
    try:
        npc = gerar_json_com_gemini(prompt)
        response = supabase.table("npcs").insert({
            "campaign_id": campaign_id,
            "name": npc.get("name", "NPC"),
            "data": npc
        }).execute()
        return {
            "success": True,
            "data": npc,
            "id": response.data[0]["id"] if response.data else None,
            "saved_id": response.data[0]["id"] if response.data else None
        }
    except Exception as e:
        print(f"ERROR AQUI: {str(e)}")
        raise HTTPException(500, f"Erro ao criar NPC: {str(e)}")


@app.get("/npcs/{campaign_id}")
async def list_npcs(campaign_id: str):
    try:
        response = supabase.table("npcs").select("*").eq("campaign_id", campaign_id).execute()
        return {"success": True, "data": response.data}
    except Exception as e:
        raise HTTPException(500, f"Erro ao buscar NPCs: {str(e)}")


@app.delete("/npcs/{npc_id}")
async def delete_npc(npc_id: str):
    try:
        supabase.table("npcs").delete().eq("id", npc_id).execute()
        return {"success": True, "message": "NPC deletado"}
    except Exception as e:
        raise HTTPException(500, f"Erro ao deletar NPC: {str(e)}")


@app.get("/skill-description/{skill_name}")
async def get_skill_description(skill_name: str, system: str = "D&D 5e", character_context: str = ""):
    prompt = f"""
    Sistema: {system}
    Contexto do personagem: {character_context or 'Nenhum'}
    Descreva a habilidade/magia/feature chamada "{skill_name}" de forma clara e jogável.

    Retorne APENAS um JSON válido:
    {{
      "name": "...",
      "type": "magia | feature racial | feature de classe | perícia",
      "description": "Descrição completa...",
      "mechanics": "Como funciona em jogo...",
      "source": "De onde vem (raça, classe, background...)"
    }}
    """
    try:
        descricao = gerar_json_com_gemini(prompt)
        return {"success": True, "data": descricao}
    except Exception as e:
        raise HTTPException(500, f"Erro na IA: {str(e)}")

@app.get("/spells")
async def get_spells(class_name: str = "Wizard"):
    result = supabase.table('spells').select('*').eq('class_name', class_name).execute()
    return {"success": True, "data": result.data}


@app.get("/")
async def root():
    return {"status": "RPG IA Backend rodando!", "version": "1.0"}

@app.get("/magic-items")
async def get_magic_items():
    try:
        response = supabase.table("magic_items").select("*").order("name").execute()
        return {"success": True, "data": response.data}
    except Exception as e:
        raise HTTPException(500, f"Erro ao buscar itens mágicos: {str(e)}")

class MagicItemRequest(BaseModel):
    name: str
    class_name: str = ""
    rarity: str = ""
    nome_misterioso: str = ""
    identificado: bool = False
    contexto: str = ""


@app.get("/session-state/{campaign_id}")
async def get_session_state(campaign_id: str):
    try:
        response = supabase.table("session_state").select("*").eq("campaign_id", campaign_id).execute()
        if response.data:
            return {"success": True, "data": response.data[0]}
        return {"success": True, "data": None}
    except Exception as e:
        raise HTTPException(500, f"Erro ao buscar estado: {str(e)}")

class SessionRequest(BaseModel):
    campaign_id: str
    title: str
    summary: str = ""
    session_number: int = 1

@app.get("/sessions/{campaign_id}")
async def get_sessions(campaign_id: str):
    try:
        response = supabase.table("sessions").select("*").eq("campaign_id", campaign_id).order("session_number", desc=True).execute()
        return {"success": True, "data": response.data}
    except Exception as e:
        raise HTTPException(500, f"Erro ao buscar sessões: {str(e)}")


@app.get("/boato")
async def gerar_boato():
    import random

    # Busca contexto do mundo atual
    eventos_ativos = supabase.table("world_events").select("name, description, progress").eq("campaign_id", CAMPANHA_ID).eq("status", "ativo").execute().data
    eventos_concluidos = supabase.table("world_events").select("name, consequences").eq("campaign_id", CAMPANHA_ID).eq("status", "concluido").execute().data
    flags_ativas = supabase.table("campaign_flags").select("key, description").eq("campaign_id", CAMPANHA_ID).eq("value", True).execute().data

    contexto_mundo = ""
    if eventos_ativos:
        contexto_mundo += "Eventos em andamento no mundo:\n" + "\n".join([f"- {e['name']} ({e['progress']}%): {e.get('description', '')}" for e in eventos_ativos])
    if eventos_concluidos:
        contexto_mundo += "\n\nEventos já concluídos:\n" + "\n".join([f"- {e['name']}: {e.get('consequences', '')}" for e in eventos_concluidos])
    if flags_ativas:
        contexto_mundo += "\n\nFatos estabelecidos no mundo:\n" + "\n".join([f"- {f.get('description', f['key'])}" for f in flags_ativas])

    falso = random.random() < 0.1
    tipo = "COMPLETAMENTE FALSO e absurdo" if falso else "VERDADEIRO sobre o mundo"

    contexto_extra = f"\n\nLeve em conta o seguinte contexto atual do mundo da campanha, se fizer sentido:\n{contexto_mundo}" if contexto_mundo else ""

    prompt = f"""Você é um frequentador de taverna em um mundo de fantasia medieval. Gere um boato curto que estaria circulando na taverna. Este boato é {tipo}.{contexto_extra}
Retorne APENAS um JSON: {{"boato": "frase curta", "fonte": "quem espalha", "falso": {str(falso).lower()}}}"""

    try:
        raw = gerar_texto_com_gemini(prompt)
        raw = raw.strip().replace("```json", "").replace("```", "").strip()
        boato_data = json.loads(raw)

        try:
            supabase.table("session_events").insert({
                "campaign_id": CAMPANHA_ID,
                "tipo": "rumor",
                "descricao": f"Boato circulando: \"{boato_data.get('boato', '')}\" (fonte: {boato_data.get('fonte', 'desconhecida')})"
            }).execute()
        except Exception as log_error:
            print(f"[AVISO] Falha ao registrar evento de sessão: {log_error}")

        return {"success": True, "data": boato_data}
    except Exception as e:
        print(f"ERRO BOATO: {e}")
        raise HTTPException(500, f"Erro ao gerar boato: {str(e)}")

@app.patch("/magic-items/{item_id}/revelar")
async def revelar_item(item_id: str):
    try:
        supabase.table("magic_items").update({"identificado": True}).eq("id", item_id).execute()
        return {"success": True}
    except Exception as e:
        raise HTTPException(500, f"Erro ao revelar item: {str(e)}")

@app.post("/sessions")
async def create_session(req: SessionRequest):
    try:
        data = {
            "campaign_id": req.campaign_id,
            "title": req.title,
            "summary": req.summary,
            "session_number": req.session_number,
        }
        response = supabase.table("sessions").insert(data).execute()
        return {"success": True, "data": response.data[0]}
    except Exception as e:
        raise HTTPException(500, f"Erro ao criar sessão: {str(e)}")

@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    try:
        supabase.table("sessions").delete().eq("id", session_id).execute()
        return {"success": True}
    except Exception as e:
        raise HTTPException(500, f"Erro ao deletar sessão: {str(e)}")

@app.post("/session-state/{campaign_id}/countdown")
async def set_countdown(campaign_id: str, active: bool, duration: int = 60):
    try:
        from datetime import datetime, timedelta
        end_time = (datetime.utcnow() + timedelta(seconds=duration)).isoformat() if active else None
        data = {
            "campaign_id": campaign_id,
            "countdown_active": active,
            "countdown_end": end_time,
            "countdown_duration": duration,
            "updated_at": datetime.utcnow().isoformat()
        }
        existing = supabase.table("session_state").select("id").eq("campaign_id", campaign_id).execute()
        if existing.data:
            supabase.table("session_state").update(data).eq("campaign_id", campaign_id).execute()
        else:
            supabase.table("session_state").insert(data).execute()
        return {"success": True, "data": data}
    except Exception as e:
        raise HTTPException(500, f"Erro ao atualizar countdown: {str(e)}")


@app.post("/magic-items/homebrew")
async def create_homebrew_item(req: MagicItemRequest):
    rarity_instruction = f'A raridade DEVE ser exatamente "{req.rarity}".' if req.rarity else 'Escolha a raridade adequada ao lore do item.'

    prompt = f"""Você é um criador de conteúdo D&D 5e expert.
Crie um item mágico original chamado EXATAMENTE "{req.name}" (não altere o nome).
{rarity_instruction}
{"Contexto e lore: " + req.contexto if req.contexto else ""}'

Retorne APENAS um JSON válido neste formato:
{{
  "name": "{req.name}",
  "rarity": "Comum/Incomum/Raro/Muito Raro/Lendário",
  "type": "Arma/Armadura/Poção/Anel/Varinha/Maravilha/Outro",
  "description": "Descrição física e lore do item. Não use markdown.",
  "mechanics": "Como funciona em jogo. Não use markdown.",
  "requires_attunement": false
}}"""
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        raw = response.text.strip().replace("```json", "").replace("```", "").strip()
        item_data = json.loads(raw)
        item_data["is_homebrew"] = True
        item_data["identificado"] = req.identificado
        if req.nome_misterioso:
            item_data["nome_misterioso"] = req.nome_misterioso
        result = supabase.table("magic_items").insert(item_data).execute()
        return {"success": True, "data": item_data}
    except json.JSONDecodeError:
        raise HTTPException(400, {"error": "IA não retornou JSON válido"})
    except Exception as e:
        print(f"ERRO MAGIC ITEM: {e}")
        raise HTTPException(500, {"error": f"Erro ao criar item: {str(e)}"})


@app.post('/spells/homebrew')
async def create_homebrew_spell(req: HombrewSpellRequest):
    """
    IA cria uma magia nova baseado em nome e classe
    """

    prompt = f"""
    Você é um criador de conteúdo D&D 5e expert.

    Crie uma magia original chamada "{req.name}" para a classe {req.class_name}.

    Siga EXATAMENTE este formato JSON (sem markdown, sem explicações):
    {{
      "name": "{req.name}",
      "level": 2,
      "school": "Evocation",
      "class_name": "{req.class_name}",
      "description": "Descrição curta da magia",
      "mechanics": "Como funciona em jogo (efeitos, salvaguardas, etc)",
      "range": "60 feet",
      "duration": "Concentration, up to 1 minute",
      "components": "V, S, M"
    }}
    """

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        spell_json = gerar_texto_com_gemini(prompt)
        spell_data = json.loads(spell_json.replace("```json", "").replace("```", "").strip())

        result = supabase.table('spells').insert({
            'name': spell_data.get('name'),
            'level': spell_data.get('level'),
            'school': spell_data.get('school'),
            'class_name': spell_data.get('class_name'),
            'description': spell_data.get('description'),
            'mechanics': spell_data.get('mechanics'),
            'range': spell_data.get('range'),
            'duration': spell_data.get('duration'),
            'components': spell_data.get('components'),
            'is_homebrew': True
        }).execute()

        return {
            'success': True,
            'data': spell_data,
            'message': f"Magia '{spell_data.get('name')}' criada com sucesso!"
        }

    except json.JSONDecodeError:
        raise HTTPException(400, {"error": "IA não retornou JSON válido"})
    except Exception as e:
        print(f"ERRO HOMEBREW: {e}")
        raise HTTPException(500, {"error": f"Erro ao criar magia: {str(e)}"})

class RulesRequest(BaseModel):
    query: str
    system: str = "D&D 5e"

@app.post('/spells/homebrew')
async def create_homebrew_spell(req: HombrewSpellRequest):
    prompt = f"""
    Você é um criador de conteúdo D&D 5e expert.

    Crie uma magia original chamada "{req.name}" para a classe {req.class_name}.

    Siga EXATAMENTE este formato JSON (sem markdown, sem explicações):
    {{
      "name": "{req.name}",
      "level": 2,
      "school": "Evocation",
      "class_name": "{req.class_name}",
      "description": "Descrição curta da magia",
      "mechanics": "Como funciona em jogo (efeitos, salvaguardas, etc)",
      "range": "60 feet",
      "duration": "Concentration, up to 1 minute",
      "components": "V, S, M"
    }}
    """

    try:
        spell_json = gerar_texto_com_gemini(prompt)
        spell_json = spell_json.replace("```json", "").replace("```", "").strip()
        spell_data = json.loads(spell_json)

        result = supabase.table('spells').insert({
            'name': spell_data.get('name'),
            'level': spell_data.get('level'),
            'school': spell_data.get('school'),
            'class_name': spell_data.get('class_name'),
            'description': spell_data.get('description'),
            'mechanics': spell_data.get('mechanics'),
            'range': spell_data.get('range'),
            'duration': spell_data.get('duration'),
            'components': spell_data.get('components'),
            'is_homebrew': True
        }).execute()

        return {'success': True, 'data': spell_data, 'message': f"Magia '{spell_data.get('name')}' criada com sucesso!"}

    except json.JSONDecodeError:
        raise HTTPException(400, {"error": "IA não retornou JSON válido"})
    except Exception as e:
        print(f"ERRO HOMEBREW: {e}")
        raise HTTPException(500, {"error": f"Erro ao criar magia: {str(e)}"})


class ManualSpellRequest(BaseModel):
    name: str
    level: int = 0
    school: str = ""
    class_name: str
    description: str = ""
    mechanics: str = ""
    range: str = ""
    duration: str = ""
    components: str = ""

@app.post('/spells/manual')
async def create_manual_spell(req: ManualSpellRequest):
    if not req.name.strip():
        raise HTTPException(400, "Nome da magia é obrigatório")

    result = supabase.table('spells').insert({
        'name': req.name,
        'level': req.level,
        'school': req.school,
        'class_name': req.class_name,
        'description': req.description,
        'mechanics': req.mechanics,
        'range': req.range,
        'duration': req.duration,
        'components': req.components,
        'is_homebrew': True
    }).execute()

    return {
        'success': True,
        'data': result.data[0] if result.data else None,
        'message': f"Magia '{req.name}' criada com sucesso!"
    }

@app.post("/rules/search")
async def search_rules(req: RulesRequest):
    prompt = f"""Você é um especialista em {req.system}.
O mestre perguntou: "{req.query}"

Responda de forma DIRETA e CONCISA como se fosse uma consulta rápida no livro de regras.
Sem introduções. Vá direto ao ponto.

Retorne APENAS um JSON válido neste formato:
{{
  "titulo": "Nome da regra/condição",
  "resumo": "Explicação curta em 1-2 frases",
  "detalhes": "Regra completa com todos os efeitos mecânicos",
  "fonte": "Nome do livro/seção onde encontrar (ex: Livro do Jogador p.290)"
}}"""

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        raw = response.text.strip().replace("```json", "").replace("```", "").strip()
        regra = json.loads(raw)
        return {"success": True, "data": regra}
    except json.JSONDecodeError:
        raise HTTPException(400, {"error": "IA não retornou JSON válido"})
    except Exception as e:
        print(f"ERRO RULES: {e}")
        raise HTTPException(500, {"error": f"Erro ao buscar regra: {str(e)}"})

class EncountroRequest(BaseModel):
    bioma: str = "floresta"
    nivel: int = 5
    contexto: str = ""

@app.post("/encounter/generate")
async def generate_encounter(req: EncountroRequest):
    prompt = f"""Você é um mestre de D&D 5e experiente.
Gere um encontro aleatório para um grupo de nível {req.nivel} em {req.bioma}.
{f'Contexto adicional: {req.contexto}' if req.contexto else ''}

Retorne APENAS um JSON válido:
{{
  "titulo": "Nome do encontro",
  "descricao": "Descrição atmosférica da cena em 2-3 frases",
  "inimigos": [
    {{"nome": "Nome do inimigo", "quantidade": 2, "cr": "1/2"}}
  ],
  "diferencial": "Um elemento surpresa ou twist do encontro",
  "recompensa": "Sugestão de recompensa (XP e itens)"
}}"""
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[{"role": "user", "parts": [{"text": prompt}]}]
        )
        raw = response.text.strip().replace("```json", "").replace("```", "").strip()
        return {"success": True, "data": json.loads(raw)}
    except json.JSONDecodeError:
        raise HTTPException(400, {"error": "IA não retornou JSON válido"})
    except Exception as e:
        print(f"ERRO ENCOUNTER: {e}")
        raise HTTPException(500, {"error": f"Erro ao gerar encontro: {str(e)}"})

class SecretMessageRequest(BaseModel):
    campaign_id: str
    character_id: str
    message: str


@app.post("/secret-messages")
async def send_secret_message(req: SecretMessageRequest):
    try:
        data = {
            "campaign_id": req.campaign_id,
            "character_id": req.character_id,
            "message": req.message,
            "lida": False
        }
        response = supabase.table("secret_messages").insert(data).execute()

        # Busca o user_id do personagem pra saber pra qual dispositivo mandar
        char_res = supabase.table("characters") \
            .select("user_id") \
            .eq("id", req.character_id) \
            .single() \
            .execute()

        # Se o personagem tiver dono, manda push notification
        if char_res.data and char_res.data.get("user_id"):
            await enviar_push_notification(
                char_res.data["user_id"],
                "🔮 Sussurro do Mestre",
                req.message
            )

        return {"success": True, "data": response.data[0]}
    except Exception as e:
        raise HTTPException(500, f"Erro ao enviar mensagem: {str(e)}")


class ProfileLoginRequest(BaseModel):
    username: str


@app.post("/profiles/login")
async def profile_login(req: ProfileLoginRequest):
    try:
        # Busca por username
        res = supabase.table("profiles").select("*").eq("username", req.username).execute()

        if res.data:
            return {"success": True, "data": res.data[0]}

        # Cria novo profile
        novo = supabase.table("profiles").insert({
            "id": str(uuid.uuid4()),
            "username": req.username,
            "role": "jogador"
        }).execute()
        return {"success": True, "data": novo.data[0]}
    except Exception as e:
        print(f"ERRO PROFILE LOGIN: {str(e)}")
        raise HTTPException(500, f"Erro ao fazer login: {str(e)}")

@app.get("/secret-messages/{character_id}")
async def get_secret_messages(character_id: str):
    try:
        response = supabase.table("secret_messages").select("*").eq("character_id", character_id).eq("lida", False).execute()
        return {"success": True, "data": response.data}
    except Exception as e:
        raise HTTPException(500, f"Erro ao buscar mensagens: {str(e)}")

@app.get("/arquetipos/{class_name}")
async def get_arquetipos(class_name: str):
    info = ARQUETIPOS_POR_CLASSE.get(class_name)
    if not info:
        return {"nivel": 3, "arquetipos": []}
    return info

@app.patch("/secret-messages/{message_id}/lida")
async def mark_as_read(message_id: str):
    try:
        supabase.table("secret_messages").update({"lida": True}).eq("id", message_id).execute()
        return {"success": True}
    except Exception as e:
        raise HTTPException(500, f"Erro ao marcar mensagem: {str(e)}")

@app.delete("/magic-items/{item_id}")
async def delete_magic_item(item_id: str):
    try:
        print(f"Deletando item: {item_id}")
        result = supabase.table("magic_items").delete().eq("id", item_id).execute()
        print(f"Resultado: {result.data}")
        return {"success": True}
    except Exception as e:
        raise HTTPException(500, f"Erro ao deletar item: {str(e)}")

@app.patch("/characters/{character_id}")
async def patch_character(character_id: str, req: dict = Body(...)):
    try:
        response = supabase.table("characters").update(req).eq("id", character_id).execute()
        return {"success": True, "data": response.data}
    except Exception as e:
        raise HTTPException(500, f"Erro ao atualizar: {str(e)}")


@app.get("/bestiary")
async def get_bestiary(name: str = "", cr: str = "", type: str = ""):
    try:
        query = supabase.table("bestiary").select("*")
        if name:
            query = query.ilike("name", f"%{name}%")
        if cr:
            query = query.eq("cr", cr)
        if type:
            query = query.eq("type", type)
        result = query.order("name").execute()
        return {"success": True, "data": result.data}
    except Exception as e:
        raise HTTPException(500, f"Erro ao buscar bestiário: {str(e)}")


@app.post("/bestiary/generate")
@limiter.limit("10/minute")
async def generate_bestiary(request: Request, nome: str, cr: str = "", tipo: str = "", descricao: str = ""):
    cr_instruction = f'O CR DEVE ser exatamente "{cr}".' if cr else 'Escolha o CR adequado.'
    tipo_instruction = f'O tipo DEVE ser "{tipo}".' if tipo else ''

    prompt = f"""Você é um mestre experiente de D&D 5e. Crie um monstro/criatura para o bestiário.
Nome: {nome}
{cr_instruction}
{tipo_instruction}
Descrição adicional: {descricao or 'Nenhuma'}

Retorne APENAS um JSON válido:
{{
  "name": "{nome}",
  "cr": "1",
  "type": "Humanoide",
  "size": "Médio",
  "alignment": "Neutro",
  "hp": 45,
  "hp_dice": "6d8+12",
  "ac": 14,
  "ac_type": "Armadura de couro",
  "speed": "9 metros",
  "attributes": {{"str": 16, "dex": 13, "con": 14, "int": 10, "wis": 11, "cha": 8}},
  "saving_throws": {{}},
  "skills": {{}},
  "damage_resistances": "",
  "damage_immunities": "",
  "condition_immunities": "",
  "senses": "Visão normal 18 metros",
  "languages": "Comum",
  "features": [{{"name": "Resistência à Magia", "description": "Tem vantagem em salvaguardas contra magias."}}],
  "actions": [{{"name": "Golpe de Espada", "description": "Ataque com arma corpo a corpo: +5 para acertar, alcance 1,5m, 1d8+3 dano cortante."}}],
  "bonus_actions": [],
  "reactions": [],
  "legendary_actions": [],
  "description": "Descrição do monstro...",
  "is_homebrew": true
}}"""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[{"role": "user", "parts": [{"text": prompt}]}]
        )
        raw = response.text.strip().replace("```json", "").replace("```", "").strip()
        monstro = json.loads(raw)
        monstro["is_homebrew"] = True
        result = supabase.table("bestiary").insert(monstro).execute()
        monstro["id"] = result.data[0]["id"] if result.data else None
        return {"success": True, "data": monstro}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Erro ao gerar monstro: {str(e)}")


@app.delete("/bestiary/{monster_id}")
async def delete_monster(monster_id: str):
    try:
        supabase.table("bestiary").delete().eq("id", monster_id).execute()
        return {"success": True}
    except Exception as e:
        raise HTTPException(500, f"Erro ao deletar monstro: {str(e)}")


@app.post("/gallery/upload")
async def upload_gallery(
        file: UploadFile = File(...),
        campaign_id: str = "",
        type: str = Form("map"),
        category: str = Form("")
):
    try:
        contents = await file.read()
        filename = f"{uuid.uuid4()}_{file.filename}"

        supabase.storage.from_("gallery").upload(
            filename,
            contents,
            {"content-type": file.content_type}
        )

        url = supabase.storage.from_("gallery").get_public_url(filename)

        data = {
            "name": file.filename,
            "url": url,
            "type": type,
            "category": category,
            "revealed": False,
        }
        if campaign_id:
            data["campaign_id"] = campaign_id

        res = supabase.table("gallery").insert(data).execute()
        return {"success": True, "data": res.data[0]}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Erro ao fazer upload: {str(e)}")


@app.get("/gallery")
async def get_gallery(campaign_id: str = ""):
    try:
        query = supabase.table("gallery").select("*").order("created_at", desc=True)
        if campaign_id:
            query = query.eq("campaign_id", campaign_id)
        res = query.execute()
        return {"success": True, "data": res.data}
    except Exception as e:
        raise HTTPException(500, f"Erro ao buscar galeria: {str(e)}")


@app.patch("/gallery/{image_id}/reveal")
async def reveal_image(image_id: str):
    try:
        # Tira o reveal de todas primeiro
        supabase.table("gallery").update({"revealed": False}).neq("id",
                                                                  "00000000-0000-0000-0000-000000000000").execute()
        # Revela só essa
        res = supabase.table("gallery").update({"revealed": True}).eq("id", image_id).execute()
        return {"success": True, "data": res.data[0]}
    except Exception as e:
        raise HTTPException(500, f"Erro ao revelar imagem: {str(e)}")


@app.patch("/gallery/{image_id}/hide")
async def hide_image(image_id: str):
    try:
        res = supabase.table("gallery").update({"revealed": False}).eq("id", image_id).execute()
        return {"success": True, "data": res.data[0]}
    except Exception as e:
        raise HTTPException(500, f"Erro ao esconder imagem: {str(e)}")


@app.delete("/gallery/{image_id}")
async def delete_gallery_image(image_id: str):
    try:
        res = supabase.table("gallery").select("*").eq("id", image_id).single().execute()
        image = res.data

        # Só tenta deletar do storage se realmente tiver uma URL de imagem
        if image and image.get("url"):
            filename = image["url"].split("/")[-1]
            supabase.storage.from_("gallery").remove([filename])

        supabase.table("gallery").delete().eq("id", image_id).execute()
        return {"success": True}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Erro ao deletar imagem: {str(e)}")

@app.get("/map-tokens/{campaign_id}")
async def get_map_tokens(campaign_id: str):
    try:
        res = supabase.table("map_tokens").select("*").eq("campaign_id", campaign_id).execute()
        return {"success": True, "data": res.data}
    except Exception as e:
        raise HTTPException(500, f"Erro ao buscar tokens: {str(e)}")

@app.post("/map-tokens")
async def add_map_token(data: dict = Body(...)):
    try:
        res = supabase.table("map_tokens").insert(data).execute()
        return {"success": True, "data": res.data[0]}
    except Exception as e:
        raise HTTPException(500, f"Erro ao adicionar token: {str(e)}")

@app.patch("/map-tokens/{token_id}/position")
async def update_token_position(token_id: str, data: dict = Body(...)):
    try:
        res = supabase.table("map_tokens").update({"x": data["x"], "y": data["y"]}).eq("id", token_id).execute()
        return {"success": True, "data": res.data[0]}
    except Exception as e:
        raise HTTPException(500, f"Erro ao mover token: {str(e)}")

@app.patch("/map-tokens/{token_id}/label")
async def update_token_label(token_id: str, data: dict = Body(...)):
    try:
        res = supabase.table("map_tokens").update({"label": data["label"]}).eq("id", token_id).execute()
        return {"success": True, "data": res.data[0]}
    except Exception as e:
        raise HTTPException(500, f"Erro ao atualizar label: {str(e)}")

@app.patch("/map-tokens/{token_id}/rotation")
async def update_token_rotation(token_id: str, data: dict = Body(...)):
    try:
        res = supabase.table("map_tokens").update({"rotation": data["rotation"]}).eq("id", token_id).execute()
        return {"success": True, "data": res.data[0]}
    except Exception as e:
        raise HTTPException(500, f"Erro ao rotacionar token: {str(e)}")

@app.patch("/map-tokens/{token_id}/scale")
async def update_token_scale(token_id: str, data: dict = Body(...)):
    try:
        res = supabase.table("map_tokens").update({"scale": data["scale"]}).eq("id", token_id).execute()
        return {"success": True, "data": res.data[0]}
    except Exception as e:
        raise HTTPException(500, f"Erro ao escalar token: {str(e)}")

@app.delete("/map-tokens/{token_id}")
async def delete_map_token(token_id: str):
    try:
        supabase.table("map_tokens").delete().eq("id", token_id).execute()
        return {"success": True}
    except Exception as e:
        raise HTTPException(500, f"Erro ao remover token: {str(e)}")


def gerar_codigo_campanha():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


@app.post("/campaigns")
async def criar_campanha(data: dict = Body(...)):
    try:
        codigo = gerar_codigo_campanha()
        res = supabase.table("campaigns").insert({
            "name": data.get("name"),
            "description": data.get("description", ""),
            "owner_id": data.get("owner_id"),
            "master_id": data.get("owner_id"),
            "code": codigo
        }).execute()
        return {"success": True, "data": res.data[0]}
    except Exception as e:
        raise HTTPException(500, f"Erro ao criar campanha: {str(e)}")


@app.get("/campaigns/by-owner/{owner_id}")
async def get_campanhas_by_owner(owner_id: str):
    try:
        res = supabase.table("campaigns").select("*").eq("owner_id", owner_id).execute()
        return {"success": True, "data": res.data}
    except Exception as e:
        raise HTTPException(500, f"Erro ao buscar campanhas: {str(e)}")

@app.get("/campaigns/{campaign_id}")
async def get_campanha(campaign_id: str):
    try:
        res = supabase.table("campaigns").select("*").eq("id", campaign_id).single().execute()
        return {"success": True, "data": res.data}
    except Exception as e:
        raise HTTPException(500, f"Erro ao buscar campanha: {str(e)}")


@app.post("/campaigns/join")
async def entrar_campanha(data: dict = Body(...)):
    try:
        # Busca campanha pelo código
        res = supabase.table("campaigns").select("*").eq("code", data.get("code").upper()).single().execute()
        if not res.data:
            raise HTTPException(404, "Campanha não encontrada")
        campanha = res.data

        # Adiciona membro
        supabase.table("campaign_members").insert({
            "campaign_id": campanha["id"],
            "user_id": data.get("user_id"),
            "role": "jogador"
        }).execute()

        return {"success": True, "data": campanha}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Erro ao entrar na campanha: {str(e)}")


@app.get("/campaigns/members/{campaign_id}")
async def get_membros(campaign_id: str):
    try:
        res = supabase.table("campaign_members").select("*, profiles(*)").eq("campaign_id", campaign_id).execute()
        return {"success": True, "data": res.data}
    except Exception as e:
        raise HTTPException(500, f"Erro ao buscar membros: {str(e)}")


@app.post("/push/subscribe")
async def salvar_subscription(data: dict = Body(...)):
    """
    Salva a assinatura do dispositivo do usuário.
    Quando o usuário aceita notificações, o browser gera uma assinatura única
    pra aquele dispositivo. A gente salva isso aqui pra usar depois.
    """
    try:
        user_id = data.get("user_id")
        subscription = data.get("subscription")

        # Verifica se já tem assinatura pra esse dispositivo
        # (evita duplicatas se o usuário abrir o site várias vezes)
        existing = supabase.table("push_subscriptions") \
            .select("*") \
            .eq("user_id", user_id) \
            .execute()

        if existing.data:
            # Atualiza a assinatura existente
            supabase.table("push_subscriptions") \
                .update({"subscription": subscription}) \
                .eq("user_id", user_id) \
                .execute()
        else:
            # Cria nova assinatura
            supabase.table("push_subscriptions") \
                .insert({"user_id": user_id, "subscription": subscription}) \
                .execute()

        return {"success": True}
    except Exception as e:
        raise HTTPException(500, f"Erro ao salvar subscription: {str(e)}")


@app.post("/notify/item")
async def notificar_item(data: dict = Body(...)):
    try:
        character_id = data.get("character_id")
        item_nome = data.get("item_nome")

        # Busca user_id e campaign_id do personagem destinatário
        char_res = supabase.table("characters") \
            .select("user_id, campaign_id, name") \
            .eq("id", character_id) \
            .single() \
            .execute()

        if char_res.data and char_res.data.get("user_id"):
            await enviar_push_notification(
                char_res.data["user_id"],
                "📦 Item Recebido",
                f"Você recebeu: {item_nome}"
            )

        # Registra o evento pra memória da sessão — falha aqui não pode quebrar a notificação
        if char_res.data and char_res.data.get("campaign_id"):
            try:
                nome_personagem = char_res.data.get("name", "um personagem")
                supabase.table("session_events").insert({
                    "campaign_id": char_res.data["campaign_id"],
                    "tipo": "item_entregue",
                    "descricao": f"{item_nome} foi entregue a {nome_personagem}"
                }).execute()
            except Exception as log_error:
                print(f"[AVISO] Falha ao registrar evento de sessão: {log_error}")

        return {"success": True}
    except Exception as e:
        raise HTTPException(500, f"Erro ao notificar: {str(e)}")


@app.post("/characters/{character_id}/avatar")
async def upload_avatar(character_id: str, file: UploadFile = File(...)):
    try:
        contents = await file.read()
        filename = f"{character_id}.{file.filename.split('.')[-1]}"
        print(f"AVATAR: filename={filename}, size={len(contents)}, type={file.content_type}")

        supabase.storage.from_("Avatars").upload(
            filename,
            contents,
            {"content-type": file.content_type, "upsert": "true"}
        )

        url = supabase.storage.from_("Avatars").get_public_url(filename)
        print(f"AVATAR URL: {url}")

        supabase.table("characters").update({"avatar_url": url}).eq("id", character_id).execute()

        return {"success": True, "url": url}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Erro ao fazer upload do avatar: {str(e)}")


@app.get("/push/vapid-public-key")
async def get_vapid_public_key():
    """
    Retorna a chave pública VAPID pro frontend.
    O browser precisa dessa chave pra criar a assinatura do dispositivo.
    É seguro expor — é a "fechadura", não a "chave".
    """
    return {"public_key": VAPID_PUBLIC_KEY}


async def enviar_push_notification(user_id: str, titulo: str, mensagem: str):
    try:
        res = supabase.table("push_subscriptions") \
            .select("*") \
            .eq("user_id", user_id) \
            .execute()

        if not res.data:
            return

        payload = json.dumps({
            "title": titulo,
            "body": mensagem,
            "icon": "/logo192.png"
        })

        # Salva a chave em arquivo temporário
        key_pem = VAPID_PRIVATE_KEY.replace('\\n', '\n')
        with tempfile.NamedTemporaryFile(mode='w', suffix='.pem', delete=False) as f:
            f.write(key_pem)
            temp_path = f.name

        try:
            for sub in res.data:
                try:
                    webpush(
                        subscription_info=sub["subscription"],
                        data=payload,
                        vapid_private_key=temp_path,
                        vapid_claims=VAPID_CLAIMS
                    )
                except WebPushException as e:
                    print(f"Erro ao enviar push: {e}")
                    if e.response and e.response.status_code == 410:
                        supabase.table("push_subscriptions") \
                            .delete() \
                            .eq("id", sub["id"]) \
                            .execute()
        finally:
            os.unlink(temp_path)  # deleta o arquivo temporário

    except Exception as e:
        print(f"Erro no push notification: {str(e)}")

@app.get("/debug/vapid")
async def debug_vapid():
    return {
        "public_key_exists": bool(VAPID_PUBLIC_KEY),
        "private_key_exists": bool(VAPID_PRIVATE_KEY),
        "public_key_preview": VAPID_PUBLIC_KEY[:20] if VAPID_PUBLIC_KEY else None
    }


@app.get("/bestiary/random-description")
async def bestiary_random_description():
    try:
        # Busca todos os monstros
        res = supabase.table("bestiary").select("name, type, cr, description").execute()
        if not res.data:
            raise HTTPException(404, "Nenhum monstro encontrado")

        # Escolhe um aleatório
        monstro = random.choice(res.data)

        prompt = f"""Você é um narrador de RPG de fantasia sombria.
Escreva uma descrição atmosférica e ameaçadora de 3 a 4 frases sobre o monstro "{monstro['name']}" (tipo: {monstro['type']}, CR {monstro['cr']}).
Foque na aparência, presença e o que os aventureiros sentem ao se deparar com ele.
Não mencione stats ou números. Escreva em português.
Responda APENAS com a descrição, sem título ou introdução."""

        descricao = gerar_texto_com_gemini(prompt)

        return {
            "success": True,
            "data": {
                "nome": monstro["name"],
                "tipo": monstro["type"],
                "cr": monstro["cr"],
                "descricao": descricao
            }
        }
    except Exception as e:
        raise HTTPException(500, f"Erro ao gerar descrição: {str(e)}")

@app.post("/aplicar-asi")
@limiter.limit("10/minute")
async def aplicar_asi(request: Request, req: AsiRequest):
    ficha = req.ficha_atual
    atributos = ficha.get("atributos", ficha.get("attributes", {}))
    pontos_disponiveis = ficha.get("asi_points", 0) + 2  # +2 do ASI deste nível

    if req.tipo == "atributos":
        if not req.alocacao:
            raise HTTPException(400, "Envie a alocação de pontos")

        custo_total = 0
        simulado = dict(atributos)
        for attr, delta in req.alocacao.items():
            if attr not in atributos:
                raise HTTPException(400, f"Atributo '{attr}' inválido")
            valor = simulado[attr]
            for _ in range(delta):
                custo_total += 2 if valor >= 18 else 1
                valor += 1
            if valor > 20:
                raise HTTPException(400, f"'{attr}' não pode passar de 20")
            simulado[attr] = valor

        if custo_total > pontos_disponiveis:
            raise HTTPException(400, f"Pontos insuficientes: precisa {custo_total}, tem {pontos_disponiveis}")

        for attr, delta in req.alocacao.items():
            atributos[attr] += delta

        ficha["atributos"] = atributos
        ficha["asi_points"] = pontos_disponiveis - custo_total

    elif req.tipo == "feat":
        if not req.feat_nome:
            raise HTTPException(400, "Informe o nome do feat")
        feats = ficha.get("feats", [])
        feats.append({"nome": req.feat_nome, "descricao": req.feat_descricao or ""})
        ficha["feats"] = feats
        ficha["asi_points"] = pontos_disponiveis  # não gastou nada nos atributos, fica banked

    else:
        raise HTTPException(400, "Tipo inválido")

    # marca esse nível/classe como resolvido pra não pedir de novo
    historico = ficha.get("asi_historico", {})
    niveis = historico.get(req.class_name, [])
    if req.nivel_alvo not in niveis:
        niveis.append(req.nivel_alvo)
    historico[req.class_name] = niveis
    ficha["asi_historico"] = historico

    supabase.table("characters").update({"data": ficha}).eq("id", req.character_id).execute()
    return {"success": True, "data": ficha}

def montar_prompt_imagem_npc(descricao_pt):
    prompt_tradutor = f"""
    Você vai gerar uma descrição visual RICA e ESPECÍFICA para um gerador de imagens de IA.

    Baseado na descrição de um NPC de RPG abaixo, crie uma lista de elementos visuais concretos em inglês.
    Se a descrição for vaga ou incompleta, INVENTE detalhes plausíveis e específicos que combinem com o contexto 
    (raça, classe, ocupação, personalidade) — nunca deixe genérico.

    Inclua obrigatoriamente: tipo de roupa/armadura, cor de cabelo e olhos, expressão facial, 
    postura corporal, e pelo menos um detalhe distintivo (cicatriz, joia, tatuagem, acessório).

    Responda APENAS com a lista de elementos separados por vírgula, sem explicações, sem frases completas.

    Descrição: {descricao_pt}
    """
    try:
        elementos_visuais = gerar_texto_com_gemini(prompt_tradutor)
        return elementos_visuais.strip()
    except Exception:
        return descricao_pt


def montar_prompt_imagem_item(descricao_pt):
    prompt_tradutor = f"""
    Você vai gerar uma descrição visual RICA e ESPECÍFICA para um gerador de imagens de IA.

    Baseado na descrição de um item mágico de RPG abaixo, crie uma lista de elementos visuais concretos em inglês.
    Se a descrição for vaga ou incompleta, INVENTE detalhes plausíveis que combinem com o tipo e raridade do item
    (material, cor, brilho, gravações, efeito mágico visível) — nunca deixe genérico.

    Responda APENAS com a lista de elementos separados por vírgula, sem explicações, sem frases completas.

    Descrição: {descricao_pt}
    """
    try:
        elementos_visuais = gerar_texto_com_gemini(prompt_tradutor)
        return elementos_visuais.strip()
    except Exception:
        return descricao_pt


@app.post("/gerar-arte")
async def gerar_arte(req: GerarArteRequest):

    if req.tipo == "npc":
        result = supabase.table("npcs").select("*").eq("id", req.id).single().execute()
        npc = result.data
        if not npc:
            raise HTTPException(404, "NPC não encontrado")

        d = npc.get("data", {}) or {}

        if req.descricao_customizada.strip():
            elementos = montar_prompt_imagem_npc(req.descricao_customizada)
        else:
            partes = [d.get('race', ''), d.get('class', d.get('occupation', '')), d.get('appearance', ''),
                      d.get('personality', '')]
            descricao_completa = ', '.join(p for p in partes if p)
            elementos = montar_prompt_imagem_npc(descricao_completa)

        prompt = f"fantasy character portrait, {elementos}, detailed digital painting, dnd art style, upper body, detailed face"
        tabela = "npcs"

    elif req.tipo == "item":
        result = supabase.table("magic_items").select("*").eq("id", req.id).single().execute()
        item = result.data
        if not item:
            raise HTTPException(404, "Item não encontrado")

        if req.descricao_customizada.strip():
            elementos = montar_prompt_imagem_item(req.descricao_customizada)
        else:
            partes = [item.get('name', ''), item.get('rarity', ''), item.get('description', '')]
            descricao_completa = ', '.join(p for p in partes if p)
            elementos = montar_prompt_imagem_item(descricao_completa)

        prompt = f"fantasy magic item icon, {elementos}, detailed illustration, isolated on dark background, glowing magic effect"
        tabela = "magic_items"

    else:
        raise HTTPException(400, "Tipo inválido")

    prompt_encoded = urllib.parse.quote(prompt)
    seed = random.randint(1, 999999)
    image_url = f"https://image.pollinations.ai/prompt/{prompt_encoded}?width=768&height=768&nologo=true&seed={seed}&model=flux"

    if req.tipo == "npc":
        d["art_url"] = image_url
        supabase.table(tabela).update({"data": d}).eq("id", req.id).execute()
    else:
        supabase.table(tabela).update({"art_url": image_url}).eq("id", req.id).execute()

    return {"success": True, "art_url": image_url}

@app.post("/deletar-arte")
async def deletar_arte(req: DeletarArteRequest):
    if req.tipo == "npc":
        result = supabase.table("npcs").select("*").eq("id", req.id).single().execute()
        npc = result.data
        if not npc:
            raise HTTPException(404, "NPC não encontrado")
        d = npc.get("data", {}) or {}
        d.pop("art_url", None)
        supabase.table("npcs").update({"data": d}).eq("id", req.id).execute()

    elif req.tipo == "item":
        supabase.table("magic_items").update({"art_url": None}).eq("id", req.id).execute()

    else:
        raise HTTPException(400, "Tipo inválido")

    return {"success": True}

@app.post("/sessions/encerrar")
async def encerrar_sessao(req: EncerrarSessaoRequest):
    ultimas = supabase.table("sessions").select("*").eq("campaign_id", req.campaign_id).order("session_number", desc=True).limit(1).execute()
    ultimo_numero = ultimas.data[0]["session_number"] if ultimas.data else 0
    data_corte = ultimas.data[0]["created_at"] if ultimas.data else "2000-01-01"

    eventos = supabase.table("session_events").select("*").eq("campaign_id", req.campaign_id).gt("created_at", data_corte).execute().data

    if not eventos:
        raise HTTPException(400, "Nenhum evento novo desde a última sessão")

    eventos_texto = "\n".join([f"- {e['tipo']}: {e['descricao']}" for e in eventos])

    prompt = f"""
    Você é um cronista de campanha de RPG. Baseado nos eventos abaixo, 
    escreva um resumo narrativo curto (3-5 frases) da sessão, em tom de "recapitulação" 
    — o que aconteceu, quem apareceu, o que mudou no mundo. Seja envolvente, não uma lista seca.

    IMPORTANTE: responda APENAS com o texto corrido do resumo, sem JSON, sem aspas, sem markdown, sem prefixos.

    Eventos:
    {eventos_texto}
    """

    resumo = gerar_texto_com_gemini(prompt)
    resumo = resumo.strip()

    if resumo.startswith("{"):
        try:
            resumo_json = json.loads(resumo)
            resumo = resumo_json.get("recap") or resumo_json.get("summary") or list(resumo_json.values())[0]
        except Exception:
            pass

    novo_numero = ultimo_numero + 1
    supabase.table("sessions").insert({
        "campaign_id": req.campaign_id,
        "session_number": novo_numero,
        "title": req.title or f"Sessão {novo_numero}",
        "summary": resumo
    }).execute()

    eventos_avancados = []
    try:
        eventos_ativos = supabase.table("world_events").select("*") \
            .eq("campaign_id", req.campaign_id) \
            .eq("status", "ativo") \
            .eq("locked_by_master", False) \
            .execute()

        for evento in eventos_ativos.data:
            # Verifica se o evento foi mencionado nos eventos da sessão
            mencionado = any(
                evento["name"].lower() in ev["descricao"].lower()
                for ev in eventos
            )
            if not mencionado:
                novo_progresso = min(100, evento.get("progress", 0) + 15)
                supabase.table("world_events").update({
                    "progress": novo_progresso,
                    "status": "concluido" if novo_progresso >= 100 else "ativo"
                }).eq("id", evento["id"]).execute()

                eventos_avancados.append({
                    "name": evento["name"],
                    "progress_antes": evento.get("progress", 0),
                    "progress_depois": novo_progresso
                })

                # NOVO: propaga consequências se completou
                if novo_progresso >= 100:
                    propagar_consequencias_evento(evento, req.campaign_id)

                # registra no log permanente do mundo
                supabase.table("world_log").insert({
                    "campaign_id": req.campaign_id,
                    "session_number": novo_numero,
                    "event_name": evento["name"],
                    "description": f"{evento['name']} avançou de {evento.get('progress', 0)}% para {novo_progresso}% enquanto os jogadores estavam ausentes."
                }).execute()

                # Dispara cadeia se completou (mesma lógica do PATCH manual)
                if novo_progresso >= 100 and evento.get("next_event_name") and not evento.get("triggered_event_id"):
                    novo_evento = supabase.table("world_events").insert({
                        "campaign_id": req.campaign_id,
                        "name": evento["next_event_name"],
                        "description": evento.get("next_event_description", ""),
                        "progress": 0,
                        "status": "ativo"
                    }).execute()
                    if novo_evento.data:
                        supabase.table("world_events").update({
                            "triggered_event_id": novo_evento.data[0]["id"]
                        }).eq("id", evento["id"]).execute()

                    supabase.table("world_log").insert({
                        "campaign_id": req.campaign_id,
                        "session_number": novo_numero,
                        "event_name": evento["next_event_name"],
                        "description": f"Novo evento surgiu como consequência de \"{evento['name']}\": {evento['next_event_name']}."
                    }).execute()

    except Exception as log_error:
        print(f"[AVISO] Falha ao processar Mundo Vivo: {log_error}")

    return {"success": True, "summary": resumo, "session_number": novo_numero, "eventos_avancados": eventos_avancados}

@app.get("/world-log/{campaign_id}")
async def listar_world_log(campaign_id: str):
    result = supabase.table("world_log").select("*").eq("campaign_id", campaign_id).order("created_at", desc=True).execute()
    return {"success": True, "data": result.data}

class FactionRequest(BaseModel):
    campaign_id: str
    description: str
    system: str = "D&D 5e"

@app.post("/factions/generate")
async def gerar_faccao(req: FactionRequest):
    prompt = f"""
    Você é um mestre de RPG criando uma facção para o mundo de campanha.
    Sistema: {req.system}
    Descrição fornecida pelo mestre: {req.description}

    Retorne APENAS um JSON:
    {{
      "name": "Nome da Facção",
      "type": "guilda/ordem/reino/culto/outro",
      "description": "Descrição curta da facção, seus valores e estrutura",
      "goals": "Objetivos atuais da facção no mundo"
    }}
    """
    try:
        raw = gerar_texto_com_gemini(prompt)
        raw = raw.replace("```json", "").replace("```", "").strip()
        faction_data = json.loads(raw)

        result = supabase.table("factions").insert({
            "campaign_id": req.campaign_id,
            "name": faction_data.get("name"),
            "type": faction_data.get("type"),
            "description": faction_data.get("description"),
            "goals": faction_data.get("goals"),
            "reputation": "neutra",
            "is_homebrew": True
        }).execute()

        return {"success": True, "data": result.data[0] if result.data else None}
    except Exception as e:
        raise HTTPException(500, f"Erro ao gerar facção: {str(e)}")


@app.get("/factions/{campaign_id}")
async def listar_faccoes(campaign_id: str):
    result = supabase.table("factions").select("*").eq("campaign_id", campaign_id).order("name").execute()
    return {"success": True, "data": result.data}


class UpdateFactionRequest(BaseModel):
    name: str = None
    type: str = None
    description: str = None
    goals: str = None
    reputation: str = None

@app.patch("/factions/{faction_id}")
async def atualizar_faccao(faction_id: str, req: UpdateFactionRequest):
    updates = {k: v for k, v in req.dict().items() if v is not None}
    supabase.table("factions").update(updates).eq("id", faction_id).execute()
    return {"success": True}


@app.delete("/factions/{faction_id}")
async def deletar_faccao(faction_id: str):
    supabase.table("factions").delete().eq("id", faction_id).execute()
    return {"success": True}

class DescricaoContextualRequest(BaseModel):
    contexto: str
    system: str = "D&D 5e"

@app.post("/gerar-descricao-contextual")
async def gerar_descricao_contextual(req: DescricaoContextualRequest):
    prompt = f"""
    Você é um mestre de RPG narrando uma cena para os jogadores.
    Sistema: {req.system}

    Baseado no contexto abaixo, escreva uma descrição imersiva e evocativa 
    (2-4 frases) pronta para ser lida em voz alta na mesa. Foque em detalhes 
    sensoriais (visão, som, cheiro, atmosfera) que ajudem os jogadores a 
    visualizar a cena.

    Contexto: {req.contexto}

    Responda APENAS com a descrição narrativa, sem título, sem explicações.
    """
    try:
        descricao = gerar_texto_com_gemini(prompt)
        return {"success": True, "data": descricao.strip()}
    except Exception as e:
        raise HTTPException(500, f"Erro ao gerar descrição: {str(e)}")

class ConsequenciaRequest(BaseModel):
    situacao: str
    system: str = "D&D 5e"

@app.post("/gerar-consequencia")
async def gerar_consequencia(req: ConsequenciaRequest):
    prompt = f"""
    Você é um mestre de RPG experiente ajudando outro mestre a improvisar.
    Sistema: {req.system}

    Os jogadores tomaram a seguinte ação/decisão: {req.situacao}

    Sugira 3 possíveis consequências ou desdobramentos plausíveis para essa ação,
    variando entre um resultado favorável, um neutro/complicado, e um desfavorável.
    Seja específico e prático, algo que o mestre possa usar imediatamente na mesa.

    Retorne APENAS um JSON:
    {{
      "favoravel": "descrição da consequência favorável",
      "neutro": "descrição da consequência neutra/complicada",
      "desfavoravel": "descrição da consequência desfavorável"
    }}
    """
    try:
        raw = gerar_texto_com_gemini(prompt)
        raw = raw.replace("```json", "").replace("```", "").strip()
        consequencias = json.loads(raw)
        return {"success": True, "data": consequencias}
    except Exception as e:
        raise HTTPException(500, f"Erro ao gerar consequência: {str(e)}")


class MemoriaNpcRequest(BaseModel):
    npc_id: str
    evento: str

@app.post("/npcs/memoria")
async def adicionar_memoria_npc(req: MemoriaNpcRequest):
    result = supabase.table("npcs").select("*").eq("id", req.npc_id).single().execute()
    npc = result.data
    if not npc:
        raise HTTPException(404, "NPC não encontrado")

    d = npc.get("data", {}) or {}
    memoria = d.get("memoria", [])
    memoria.append({"evento": req.evento, "data": datetime.now().isoformat()})
    d["memoria"] = memoria[-20:]  # mantém só os últimos 20 eventos

    supabase.table("npcs").update({"data": d}).eq("id", req.npc_id).execute()
    return {"success": True, "data": d["memoria"]}


class SugestaoNpcRequest(BaseModel):
    npc_id: str
    situacao_atual: str = ""

@app.post("/npcs/sugerir-acao")
async def sugerir_acao_npc(req: SugestaoNpcRequest):
    result = supabase.table("npcs").select("*").eq("id", req.npc_id).single().execute()
    npc = result.data
    if not npc:
        raise HTTPException(404, "NPC não encontrado")

    d = npc.get("data", {}) or {}
    memoria = d.get("memoria", [])
    memoria_texto = "\n".join([f"- {m['evento']}" for m in memoria]) or "Nenhum evento registrado ainda."

    prompt = f"""
    Você é um mestre de RPG interpretando um NPC.

    Nome: {d.get('name', npc.get('name'))}
    Personalidade: {d.get('personality', 'não definida')}
    Motivação: {d.get('motivation', 'não definida')}

    Histórico de interações com os jogadores:
    {memoria_texto}

    Situação atual: {req.situacao_atual or "Os jogadores acabam de encontrar este NPC novamente."}

    Baseado na personalidade e no histórico acima, sugira como esse NPC reagiria 
    agora — o que ele diria ou faria. Seja específico e consistente com o que já aconteceu.
    Responda em 2-4 frases, em tom narrativo, pronto para o mestre usar na mesa.
    """
    try:
        sugestao = gerar_texto_com_gemini(prompt)
        return {"success": True, "data": sugestao.strip()}
    except Exception as e:
        raise HTTPException(500, f"Erro ao gerar sugestão: {str(e)}")

class RemoverMemoriaRequest(BaseModel):
    npc_id: str
    index: int

@app.post("/npcs/memoria/remover")
async def remover_memoria_npc(req: RemoverMemoriaRequest):
    result = supabase.table("npcs").select("*").eq("id", req.npc_id).single().execute()
    npc = result.data
    if not npc:
        raise HTTPException(404, "NPC não encontrado")

    d = npc.get("data", {}) or {}
    memoria = d.get("memoria", [])
    if 0 <= req.index < len(memoria):
        memoria.pop(req.index)
    d["memoria"] = memoria

    supabase.table("npcs").update({"data": d}).eq("id", req.npc_id).execute()
    return {"success": True, "data": memoria}

class ConhecimentoRequest(BaseModel):
    character_id: str
    topico: str
    system: str = "D&D 5e"

@app.post("/personagem/conhecimento")
async def verificar_conhecimento(req: ConhecimentoRequest):
    result = supabase.table("characters").select("*").eq("id", req.character_id).single().execute()
    char = result.data
    if not char:
        raise HTTPException(404, "Personagem não encontrado")

    d = char.get("data", {}) or {}
    attrs = d.get("attributes", d.get("atributos", {}))
    skills = d.get("skills", {})
    classes = d.get("classes", [{"name": d.get("class")}])
    background = d.get("background", "")

    prompt = f"""
    Você é um mestre de RPG decidindo o que um personagem sabe sobre um tópico.
    Sistema: {req.system}

    Personagem: {d.get('name', char.get('name'))}
    Classe(s): {json.dumps(classes)}
    Antecedente: {background}
    Inteligência: {attrs.get('int', 10)}
    Perícias relevantes (Arcana, História, Religião, Natureza, Investigação): {json.dumps({k: v for k, v in skills.items() if k in ['arcana', 'history', 'religion', 'nature', 'investigation']})}

    Tópico perguntado: {req.topico}

    Baseado nos atributos, perícias e antecedente acima, determine se esse personagem 
    específico saberia algo sobre esse tópico. Seja realista: um personagem com baixa 
    Inteligência e sem perícias relevantes provavelmente sabe pouco ou nada, mesmo que 
    a informação seja "conhecida" geralmente.

    IMPORTANTE: responda APENAS com o texto corrido, sem JSON, sem aspas, sem markdown, sem prefixos.

    Responda em 2-3 frases, do ponto de vista do que o personagem lembra ou pensa, 
    ou explique brevemente por que ele não saberia nada sobre isso.
    """
    try:
        resposta = gerar_texto_com_gemini(prompt)
        resposta = resposta.strip()

        if resposta.startswith("{"):
            try:
                resposta_json = json.loads(resposta)
                resposta = resposta_json.get("knowledge") or resposta_json.get("resposta") or \
                           list(resposta_json.values())[0]
            except Exception:
                pass

        return {"success": True, "data": resposta}
    except Exception as e:
        raise HTTPException(500, f"Erro ao verificar conhecimento: {str(e)}")

class LocationRequest(BaseModel):
    campaign_id: str
    description: str
    system: str = "D&D 5e"

@app.post("/locations/generate")
async def gerar_local(req: LocationRequest):
    prompt = f"""
    Você é um mestre de RPG criando um local para o mundo de campanha.
    Sistema: {req.system}
    Descrição fornecida: {req.description}

    Retorne APENAS um JSON:
    {{
      "name": "Nome do Local",
      "type": "cidade/vila/masmorra/floresta/ruína/outro",
      "description": "Descrição geral do local, atmosfera e aparência",
      "region_info": "Clima, geografia e cultura da região",
      "commerce": "O que é comum encontrar à venda ou negociar aqui",
      "monsters": "Criaturas ou perigos comuns na região",
      "quests": "2-3 ideias de missão ou situação que fazem sentido aqui",
      "language": "Idioma mais falado no local",
      "avg_level": "Faixa de nível recomendada para aventureiros (ex: 3-5)",
      "boss": "Uma possível ameaça principal ou chefe local, se fizer sentido (ou vazio se não)"
    }}
    """
    try:
        raw = gerar_texto_com_gemini(prompt)
        raw = raw.replace("```json", "").replace("```", "").strip()
        loc_data = json.loads(raw)

        result = supabase.table("locations").insert({
            "campaign_id": req.campaign_id,
            "name": loc_data.get("name"),
            "type": loc_data.get("type"),
            "description": loc_data.get("description"),
            "region_info": loc_data.get("region_info"),
            "commerce": loc_data.get("commerce"),
            "monsters": loc_data.get("monsters"),
            "quests": loc_data.get("quests"),
            "language": loc_data.get("language"),
            "avg_level": loc_data.get("avg_level"),
            "boss": loc_data.get("boss"),
            "is_homebrew": True
        }).execute()

        return {"success": True, "data": result.data[0] if result.data else None}
    except Exception as e:
        raise HTTPException(500, f"Erro ao gerar local: {str(e)}")


@app.get("/locations/{campaign_id}")
async def listar_locais(campaign_id: str):
    result = supabase.table("locations").select("*").eq("campaign_id", campaign_id).order("name").execute()
    return {"success": True, "data": result.data}


class UpdateLocationRequest(BaseModel):
    faction_id: str = None
    name: str = None

@app.patch("/locations/{location_id}")
async def atualizar_local(location_id: str, req: UpdateLocationRequest):
    updates = {k: v for k, v in req.dict().items() if v is not None}
    supabase.table("locations").update(updates).eq("id", location_id).execute()
    return {"success": True}


@app.delete("/locations/{location_id}")
async def deletar_local(location_id: str):
    supabase.table("locations").delete().eq("id", location_id).execute()
    return {"success": True}

class HandoutRequest(BaseModel):
    campaign_id: str
    descricao: str
    tipo_documento: str = "carta"  # carta, bilhete, pergaminho, mapa de tesouro, etc

@app.post("/gallery/gerar-handout")
async def gerar_handout(req: HandoutRequest):
    prompt = f"""
    Você é um mestre de RPG criando um documento/handout para os jogadores encontrarem.
    Tipo: {req.tipo_documento}
    Contexto: {req.descricao}

    Escreva o conteúdo completo do documento como ele apareceria fisicamente 
    (texto da carta, bilhete, pergaminho, etc), em tom apropriado ao contexto.
    Responda APENAS com o texto do documento, sem explicações externas.
    """
    try:
        conteudo = gerar_texto_com_gemini(prompt)
        conteudo = conteudo.strip()

        result = supabase.table("gallery").insert({
            "campaign_id": req.campaign_id,
            "name": f"{req.tipo_documento.capitalize()} - {req.descricao[:40]}",
            "type": "handout",
            "category": req.tipo_documento,
            "text_content": conteudo,
            "revealed": False
        }).execute()

        return {"success": True, "data": result.data[0] if result.data else None}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Erro ao gerar handout: {str(e)}")

class WorldEventRequest(BaseModel):
    campaign_id: str
    name: str
    description: str = ""
    deadline: str = ""
    consequences: str = ""
    next_event_name: str = ""
    next_event_description: str = ""
    affects_faction_id: str = ""
    faction_reputation_change: str = ""
    sets_flag_key: str = ""

@app.post("/world-events")
async def criar_evento_mundo(req: WorldEventRequest):
    result = supabase.table("world_events").insert({
        "campaign_id": req.campaign_id,
        "name": req.name,
        "description": req.description,
        "deadline": req.deadline,
        "consequences": req.consequences,
        "next_event_name": req.next_event_name,
        "next_event_description": req.next_event_description,
        "affects_faction_id": req.affects_faction_id or None,
        "faction_reputation_change": req.faction_reputation_change or None,
        "sets_flag_key": req.sets_flag_key or None,
        "progress": 0,
        "status": "ativo"
    }).execute()
    return {"success": True, "data": result.data[0] if result.data else None}


@app.get("/world-events/{campaign_id}")
async def listar_eventos_mundo(campaign_id: str):
    result = supabase.table("world_events").select("*").eq("campaign_id", campaign_id).order("created_at").execute()
    return {"success": True, "data": result.data}


class UpdateWorldEventRequest(BaseModel):
    progress: int = None
    status: str = None
    locked_by_master: bool = None
    name: str = None
    description: str = None
    deadline: str = None
    consequences: str = None


@app.delete("/world-events/{event_id}")
async def deletar_evento_mundo(event_id: str):
    supabase.table("world_events").delete().eq("id", event_id).execute()
    return {"success": True}

@app.post("/world-events/{event_id}/sugerir")
async def sugerir_desdobramento(event_id: str):
    result = supabase.table("world_events").select("*").eq("id", event_id).single().execute()
    evento = result.data
    if not evento:
        raise HTTPException(404, "Evento não encontrado")

    prompt = f"""
    Você é um mestre de RPG ajudando outro mestre a decidir os próximos passos do mundo.

    Evento em andamento:
    Nome: {evento['name']}
    Descrição: {evento.get('description', '')}
    Progresso atual: {evento.get('progress', 0)}%
    Consequências ao concluir: {evento.get('consequences', '')}

    Sugira um desdobramento plausível e específico que poderia acontecer em breve, 
    dado o estado atual deste evento. Seja concreto, algo que o mestre possa usar 
    imediatamente na mesa (uma ação de facção, uma complicação, um sinal de que o 
    evento está avançando).

    Responda em 2-3 frases, direto ao ponto, sem introdução.
    """
    try:
        sugestao = gerar_texto_com_gemini(prompt)
        return {"success": True, "data": sugestao.strip()}
    except Exception as e:
        raise HTTPException(500, f"Erro ao gerar sugestão: {str(e)}")

@app.get("/presagios")
async def get_presagios():
    try:
        res = supabase.table("presagios").select("*").order("created_at", desc=True).execute()
        return {"success": True, "data": res.data}
    except Exception as e:
        raise HTTPException(500, f"Erro ao buscar presságios: {str(e)}")

@app.post("/presagios")
async def criar_presagio(data: dict = Body(...)):
    try:
        res = supabase.table("presagios").insert({
            "campaign_id": data.get("campaign_id", "00000000-0000-0000-0000-000000000001"),
            "texto": data.get("texto"),
            "cumprido": False
        }).execute()
        return {"success": True, "data": res.data[0]}
    except Exception as e:
        raise HTTPException(500, f"Erro ao criar presságio: {str(e)}")

@app.patch("/presagios/{id}/cumprir")
async def cumprir_presagio(id: str):
    try:
        res = supabase.table("presagios").update({"cumprido": True}).eq("id", id).execute()
        return {"success": True, "data": res.data[0]}
    except Exception as e:
        raise HTTPException(500, f"Erro ao cumprir presságio: {str(e)}")

@app.delete("/presagios/{id}")
async def deletar_presagio(id: str):
    try:
        supabase.table("presagios").delete().eq("id", id).execute()
        return {"success": True}
    except Exception as e:
        raise HTTPException(500, f"Erro ao deletar presságio: {str(e)}")

@app.patch("/bestiary/{id}/descoberto")
async def toggle_descoberto(id: str, data: dict = Body(...)):
    try:
        res = supabase.table("bestiary").update({"discovered": data.get("discovered")}).eq("id", id).execute()
        return {"success": True, "data": res.data[0]}
    except Exception as e:
        raise HTTPException(500, f"Erro ao atualizar bestiário: {str(e)}")


def propagar_consequencias_evento(evento, campaign_id):
    try:
        if evento.get("affects_faction_id") and evento.get("faction_reputation_change"):
            supabase.table("factions").update({
                "reputation": evento["faction_reputation_change"]
            }).eq("id", evento["affects_faction_id"]).execute()

        if evento.get("sets_flag_key"):
            flag_key = evento["sets_flag_key"]
            existente = supabase.table("campaign_flags").select("id").eq("campaign_id", campaign_id).eq("key", flag_key).execute()

            if existente.data:
                supabase.table("campaign_flags").update({"value": True}).eq("campaign_id", campaign_id).eq("key", flag_key).execute()
            else:
                supabase.table("campaign_flags").insert({
                    "campaign_id": campaign_id,
                    "key": flag_key,
                    "value": True,
                    "description": f"Criada automaticamente pelo evento: {evento['name']}"
                }).execute()
    except Exception as e:
        print(f"[AVISO] Falha ao propagar consequências: {e}")


@app.patch("/world-events/{event_id}")
async def atualizar_evento_mundo(event_id: str, req: UpdateWorldEventRequest):
    updates = {k: v for k, v in req.dict().items() if v is not None}

    result = supabase.table("world_events").update(updates).eq("id", event_id).execute()
    evento_atualizado = result.data[0] if result.data else None

    if evento_atualizado and evento_atualizado.get("progress", 0) >= 100:
        propagar_consequencias_evento(evento_atualizado, evento_atualizado["campaign_id"])

        # Se tem um próximo evento configurado, dispara a cadeia
        if evento_atualizado.get("next_event_name") and not evento_atualizado.get("triggered_event_id"):
            novo_evento = supabase.table("world_events").insert({
                "campaign_id": evento_atualizado["campaign_id"],
                "name": evento_atualizado["next_event_name"],
                "description": evento_atualizado.get("next_event_description", ""),
                "progress": 0,
                "status": "ativo"
            }).execute()

            if novo_evento.data:
                supabase.table("world_events").update({
                    "triggered_event_id": novo_evento.data[0]["id"]
                }).eq("id", event_id).execute()

    return {"success": True}


class FlagRequest(BaseModel):
    campaign_id: str
    key: str
    value: bool = False
    description: str = ""

@app.post("/flags")
async def criar_flag(req: FlagRequest):
    try:
        result = supabase.table("campaign_flags").insert({
            "campaign_id": req.campaign_id,
            "key": req.key,
            "value": req.value,
            "description": req.description
        }).execute()
        return {"success": True, "data": result.data[0] if result.data else None}
    except Exception as e:
        raise HTTPException(500, f"Erro ao criar flag: {str(e)}")


@app.get("/flags/{campaign_id}")
async def listar_flags(campaign_id: str):
    result = supabase.table("campaign_flags").select("*").eq("campaign_id", campaign_id).order("key").execute()
    return {"success": True, "data": result.data}


class UpdateFlagRequest(BaseModel):
    value: bool

@app.patch("/flags/{flag_id}")
async def atualizar_flag(flag_id: str, req: UpdateFlagRequest):
    supabase.table("campaign_flags").update({"value": req.value}).eq("id", flag_id).execute()
    return {"success": True}


@app.delete("/flags/{flag_id}")
async def deletar_flag(flag_id: str):
    supabase.table("campaign_flags").delete().eq("id", flag_id).execute()
    return {"success": True}

class ArquivoMestreRequest(BaseModel):
    campaign_id: str = "00000000-0000-0000-0000-000000000001"
    categoria: str
    texto: str

@app.post("/arquivo-mestre")
async def criar_arquivo_mestre(req: ArquivoMestreRequest):
    result = supabase.table("arquivo_mestre").insert({
        "campaign_id": req.campaign_id,
        "categoria": req.categoria,
        "texto": req.texto
    }).execute()
    return {"success": True, "data": result.data[0] if result.data else None}


@app.get("/arquivo-mestre/{campaign_id}")
async def listar_arquivo_mestre(campaign_id: str):
    result = supabase.table("arquivo_mestre").select("*").eq("campaign_id", campaign_id).order("created_at", desc=True).execute()
    return {"success": True, "data": result.data}


@app.delete("/arquivo-mestre/{item_id}")
async def deletar_arquivo_mestre(item_id: str):
    supabase.table("arquivo_mestre").delete().eq("id", item_id).execute()
    return {"success": True}

class ProphecyRequest(BaseModel):
    campaign_id: str = "00000000-0000-0000-0000-000000000001"
    texto: str
    condicao: str

@app.post("/prophecies")
async def criar_profecia(req: ProphecyRequest):
    result = supabase.table("prophecies").insert({
        "campaign_id": req.campaign_id,
        "texto": req.texto,
        "condicao": req.condicao,
        "status": "pendente"
    }).execute()
    return {"success": True, "data": result.data[0] if result.data else None}

@app.get("/prophecies/{campaign_id}")
async def listar_profecias(campaign_id: str):
    result = supabase.table("prophecies").select("*").eq("campaign_id", campaign_id).execute()
    return {"success": True, "data": result.data}

class UpdateProphecyRequest(BaseModel):
    status: str = None
    notas_cumprimento: str = None

@app.patch("/prophecies/{prophecy_id}")
async def atualizar_profecia(prophecy_id: str, req: UpdateProphecyRequest):
    updates = {k: v for k, v in req.dict().items() if v is not None}
    supabase.table("prophecies").update(updates).eq("id", prophecy_id).execute()
    return {"success": True}

@app.delete("/prophecies/{prophecy_id}")
async def deletar_profecia(prophecy_id: str):
    supabase.table("prophecies").delete().eq("id", prophecy_id).execute()
    return {"success": True}


class EventoRegional(BaseModel):
    campaign_id: str
    regiao: str
    tipo_evento: str
    motivo: str
    modificadores: dict  # {"comida": 1.5, "armas": 1.3, "viagem": 0.6, "comercio": 0.7}


@app.post("/economia/eventos")
def criar_evento(evento: EventoRegional):
    resp = supabase.table("eventos_regionais").insert(evento.dict()).execute()
    return resp.data[0]


@app.patch("/economia/eventos/{evento_id}/encerrar")
def encerrar_evento(evento_id: str):
    resp = supabase.table("eventos_regionais") \
        .update({"ativo": False}) \
        .eq("id", evento_id).execute()
    if not resp.data:
        raise HTTPException(404, "Evento não encontrado")
    return resp.data[0]


@app.get("/economia/eventos-campanha/{campaign_id}")
def listar_todos_eventos(campaign_id: str):
    """Lista todos os eventos regionais (ativos e encerrados) — usado pela aba MundoVivo."""
    resp = supabase.table("eventos_regionais") \
        .select("*") \
        .eq("campaign_id", campaign_id) \
        .order("data_inicio", desc=True) \
        .execute()
    return {"data": resp.data}


@app.get("/economia/precos/{campaign_id}")
def listar_precos_referencia(campaign_id: str):
    """Lista os preços base cadastrados (comida, armas, poções...)."""
    resp = supabase.table("precos_referencia").select("*").eq("campaign_id", campaign_id).execute()
    return {"data": resp.data}


@app.get("/economia/preco/{item_id}")
def preco_atual(item_id: str, regiao: str, campaign_id: str):
    item = supabase.table("precos_referencia").select("*").eq("id", item_id).single().execute().data
    if not item:
        raise HTTPException(404, "Item não encontrado")

    preco_base = item["preco_base"]
    categoria = item["categoria"]

    eventos = listar_todos_eventos(campaign_id)["data"]
    eventos_ativos = [e for e in eventos if e["ativo"] and e["regiao"] == regiao]

    multiplicador_final = 1.0
    motivos = []
    for evento in eventos_ativos:
        mod = evento["modificadores"].get(categoria)
        if mod:
            multiplicador_final *= mod
            motivos.append(evento["motivo"])

    preco_atual = round(preco_base * multiplicador_final, 2)

    return {
        "nome_item": item["nome_item"],
        "preco_atual": preco_atual,
        "preco_normal": preco_base,
        "motivo": " + ".join(motivos) if motivos else None,
    }


CHANCE_EVENTO_POR_DIA = 0.35


class IniciarViagem(BaseModel):
    campaign_id: str
    origem_id: str
    destino_id: str
    tempo_estimado_dias: float
    clima: Optional[str] = None


@app.get("/viagem/locais/{campaign_id}")
def listar_locais_para_viagem(campaign_id: str):
    """Popula os selects de origem/destino com os Locais já cadastrados."""
    resp = supabase.table("locations").select("id, name, region_info, monsters, commerce") \
        .eq("campaign_id", campaign_id).execute()
    return {"data": resp.data}


@app.post("/viagem/iniciar")
def iniciar_viagem(payload: IniciarViagem):
    viagem = payload.dict()
    resp = supabase.table("viagens").insert(viagem).execute()
    return resp.data[0]


@app.post("/viagem/{viagem_id}/avancar")
def avancar_dia(viagem_id: str):
    viagem = supabase.table("viagens").select("*").eq("id", viagem_id).single().execute().data
    if not viagem:
        raise HTTPException(404, "Viagem não encontrada")
    if viagem["status"] != "em_andamento":
        raise HTTPException(400, "Viagem já finalizada")

    dia_atual = viagem["dia_atual"] + 1
    eventos = viagem["eventos"] or []

    if random.random() < CHANCE_EVENTO_POR_DIA:
        origem = supabase.table("locations").select("*").eq("id", viagem["origem_id"]).single().execute().data
        destino = supabase.table("locations").select("*").eq("id", viagem["destino_id"]).single().execute().data

        prompt = (
            f"Gere um evento curto (1-2 frases) de estrada para uma viagem de D&D 5e, "
            f"entre '{origem['name']}' e '{destino['name']}'.\n"
            f"Contexto da região: {destino.get('region_info') or origem.get('region_info') or 'desconhecido'}.\n"
            f"Ameaças possíveis na área: {destino.get('monsters') or origem.get('monsters') or 'nenhuma informada'}.\n"
            f"Comércio/recursos da região: {destino.get('commerce') or origem.get('commerce') or 'nenhum informado'}.\n"
            f"Clima: {viagem.get('clima') or 'não especificado'}.\n"
            f"Pode ser perigo, encontro, achado ou obstáculo. Não resolva o evento, "
            f"apenas descreva a situação para o Mestre decidir o que fazer."
        )

        try:
            resposta = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
            )
            descricao = resposta.text.strip()
        except ServerError:
            descricao = "A estrada segue tranquila por hoje."

        eventos.append({"dia": dia_atual, "descricao": descricao, "resolvido": False})

    status = "concluida" if dia_atual >= viagem["tempo_estimado_dias"] else "em_andamento"

    resp = supabase.table("viagens").update({
        "dia_atual": dia_atual,
        "eventos": eventos,
        "status": status,
    }).eq("id", viagem_id).execute()

    return resp.data[0]


@app.get("/viagem/campanha/{campaign_id}")
def listar_viagens(campaign_id: str):
    resp = supabase.table("viagens") \
        .select("*, origem:origem_id(name), destino:destino_id(name)") \
        .eq("campaign_id", campaign_id) \
        .order("criado_em", desc=True) \
        .execute()
    return {"data": resp.data}

@app.get("/viagem/{viagem_id}")
def status_viagem(viagem_id: str):
    resp = supabase.table("viagens").select("*").eq("id", viagem_id).single().execute()
    if not resp.data:
        raise HTTPException(404, "Viagem não encontrada")
    return resp.data

# ===================== RODAR =====================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)