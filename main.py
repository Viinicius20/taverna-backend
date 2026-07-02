import os
import json
import uuid
import time
import fitz
import random
import string
import base64
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

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY")
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY")
VAPID_CLAIMS = {"sub": "mailto:viniciusamoury0403@gmail.com"}

def get_vapid_private_pem():
    try:
        padding = '=' * (4 - len(VAPID_PRIVATE_KEY) % 4)
        pem_bytes = base64.urlsafe_b64decode(VAPID_PRIVATE_KEY + padding)
        return pem_bytes.decode('utf-8')
    except:
        return VAPID_PRIVATE_KEY

load_dotenv()

# ===================== CONFIG =====================
app = FastAPI(title="RPG IA - Backend")

ARQUETIPOS_POR_CLASSE = {
    "Guerreiro": {"nivel": 3, "arquetipos": ["Campeão", "Cavaleiro Arcano", "Mestre de Batalha", "Cavaleiro Eldritch", "Samurai", "Lutador"]},
    "Fighter": {"nivel": 3, "arquetipos": ["Champion", "Arcane Archer", "Battle Master", "Eldritch Knight", "Samurai", "Psi Warrior"]},
    "Monge": {"nivel": 3, "arquetipos": ["Guerreiro da Mão Aberta", "Sombra", "Elemento", "Alma do Sol", "Punho Bêbado"]},
    "Monk": {"nivel": 3, "arquetipos": ["Open Hand", "Shadow", "Four Elements", "Sun Soul", "Drunken Master"]},
    "Ladino": {"nivel": 3, "arquetipos": ["Trapaceiro Arcano", "Assassino", "Ladrão", "Swashbuckler", "Inquisidor"]},
    "Rogue": {"nivel": 3, "arquetipos": ["Arcane Trickster", "Assassin", "Thief", "Swashbuckler", "Inquisitive"]},
    "Mago": {"nivel": 2, "arquetipos": ["Evocação", "Abjuração", "Ilusão", "Necromancia", "Adivinhação", "Transmutação", "Encantamento", "Conjuração"]},
    "Wizard": {"nivel": 2, "arquetipos": ["Evocation", "Abjuration", "Illusion", "Necromancy", "Divination", "Transmutation", "Enchantment", "Conjuration"]},
    "Clérigo": {"nivel": 1, "arquetipos": ["Vida", "Luz", "Conhecimento", "Guerra", "Natureza", "Tempestade", "Enganação", "Morte"]},
    "Cleric": {"nivel": 1, "arquetipos": ["Life", "Light", "Knowledge", "War", "Nature", "Tempest", "Trickery", "Death"]},
    "Bardo": {"nivel": 3, "arquetipos": ["Colégio do Saber", "Colégio do Valor", "Colégio da Criação", "Colégio da Eloquência"]},
    "Bard": {"nivel": 3, "arquetipos": ["College of Lore", "College of Valor", "College of Creation", "College of Eloquence"]},
    "Bruxo": {"nivel": 1, "arquetipos": ["Arquifada", "Ancião", "Diabo", "Gólem", "Celestial"]},
    "Warlock": {"nivel": 1, "arquetipos": ["Archfey", "Great Old One", "Fiend", "Hexblade", "Celestial"]},
    "Paladino": {"nivel": 3, "arquetipos": ["Devoção", "Vingança", "Ancestral", "Glória", "Conquista"]},
    "Paladin": {"nivel": 3, "arquetipos": ["Devotion", "Vengeance", "Ancients", "Glory", "Conquest"]},
    "Druida": {"nivel": 2, "arquetipos": ["Círculo da Lua", "Círculo da Terra", "Círculo dos Sonhos", "Círculo do Pastor"]},
    "Druid": {"nivel": 2, "arquetipos": ["Circle of the Moon", "Circle of the Land", "Circle of Dreams", "Circle of the Shepherd"]},
    "Patrulheiro": {"nivel": 3, "arquetipos": ["Caçador", "Mestre das Bestas", "Deslizador Horizonte"]},
    "Ranger": {"nivel": 3, "arquetipos": ["Hunter", "Beast Master", "Gloom Stalker"]},
    "Feiticeiro": {"nivel": 1, "arquetipos": ["Origem Dracônica", "Magia Selvagem", "Alma Divina", "Sombra"]},
    "Sorcerer": {"nivel": 1, "arquetipos": ["Draconic Bloodline", "Wild Magic", "Divine Soul", "Shadow Magic"]},
    "Bárbaro": {"nivel": 3, "arquetipos": ["Berserker", "Totem", "Zealot", "Storm Herald"]},
    "Barbarian": {"nivel": 3, "arquetipos": ["Berserker", "Totem Warrior", "Zealot", "Storm Herald"]},
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


# ===================== FUNÇÃO AUXILIAR GEMINI =====================
from google.genai.errors import ServerError
import time

GEMINI_KEYS = [
    os.getenv("GEMINI_API_KEY"),
    os.getenv("GEMINI_API_KEY_2"),
    os.getenv("GEMINI_API_KEY_3"),
    os.getenv("GEMINI_API_KEY_4"),
]

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

    arquetipo_txt = f"\nAquétipo escolhido AGORA: {req.arquetipo} — adicione todas as features deste arquétipo." if req.arquetipo else f"\nArquétipo atual: {ficha.get('arquetipo', 'nenhum')}"

    prompt = f"""
    Você é um mestre experiente de RPG. Um personagem subiu de nível.

    Sistema: {req.system}
    Nome: {ficha.get("name")}
    Raça: {ficha.get("race")}
    Classes: {json.dumps(ficha.get("classes", [{"name": ficha.get("class")}]))}
    Nível atual: {nivel_atual}
    Nível alvo: {req.nivel_alvo}
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
    - features: adicione TODAS as novas features/habilidades do nível {req.nivel_alvo}
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

    Retorne a ficha com a mesma estrutura recebida, apenas com os campos acima atualizados.
    """

    try:
        ficha_nova = gerar_json_com_gemini(prompt)

        # Preservar campos que a IA pode ignorar
        campos_preservar = ["background", "alignment", "background_story", "inventory", "xp", "classes", "name", "race"]
        for campo in campos_preservar:
            if campo in ficha and (campo not in ficha_nova or not ficha_nova[campo]):
                ficha_nova[campo] = ficha[campo]

        if req.arquetipo:
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
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[{"role": "user", "parts": parts}]
        )
        raw = response.text.strip()
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
    falso = random.random() < 0.1
    tipo = "COMPLETAMENTE FALSO e absurdo" if falso else "VERDADEIRO sobre o mundo"
    prompt = f"Você é um frequentador de taverna em um mundo de fantasia medieval. Gere um boato curto que estaria circulando na taverna. Este boato é {tipo}. Retorne APENAS um JSON: {{\"boato\": \"frase curta\", \"fonte\": \"quem espalha\", \"falso\": {str(falso).lower()}}}"

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[{"role": "user", "parts": [{"text": prompt}]}]
        )
        print(f"BOATO RAW: '{response.text}'")
        raw = response.text.strip().replace("```json", "").replace("```", "").strip()
        return {"success": True, "data": json.loads(raw)}
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
        spell_json = response.text
        spell_json = response.text
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
        # Busca a imagem pra pegar o filename
        res = supabase.table("gallery").select("*").eq("id", image_id).single().execute()
        image = res.data

        # Extrai filename da URL
        filename = image["url"].split("/")[-1]

        # Deleta do storage
        supabase.storage.from_("gallery").remove([filename])

        # Deleta da tabela
        supabase.table("gallery").delete().eq("id", image_id).execute()
        return {"success": True}
    except Exception as e:
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


@app.get("/push/vapid-public-key")
async def get_vapid_public_key():
    """
    Retorna a chave pública VAPID pro frontend.
    O browser precisa dessa chave pra criar a assinatura do dispositivo.
    É seguro expor — é a "fechadura", não a "chave".
    """
    return {"public_key": VAPID_PUBLIC_KEY}


async def enviar_push_notification(user_id: str, titulo: str, mensagem: str):
    """
    Função auxiliar que manda notificação push pra todos os dispositivos de um usuário.
    Um usuário pode ter vários dispositivos (celular + tablet + PC).
    """
    try:
        # Busca todas as assinaturas do usuário
        res = supabase.table("push_subscriptions") \
            .select("*") \
            .eq("user_id", user_id) \
            .execute()

        if not res.data:
            return  # Usuário não tem assinatura, ignora

        payload = json.dumps({
            "title": titulo,
            "body": mensagem,
            "icon": "/logo192.png"
        })

        for sub in res.data:
            try:
                webpush(
                    subscription_info=sub["subscription"],
                    data=payload,
                    vapid_private_key=get_vapid_private_pem(),
                    vapid_claims=VAPID_CLAIMS
                )
            except WebPushException as e:
                print(f"Erro ao enviar push: {e}")
                # Se a assinatura expirou, deleta do banco
                if e.response and e.response.status_code == 410:
                    supabase.table("push_subscriptions") \
                        .delete() \
                        .eq("id", sub["id"]) \
                        .execute()
    except Exception as e:
        print(f"Erro no push notification: {str(e)}")

@app.get("/debug/vapid")
async def debug_vapid():
    return {
        "public_key_exists": bool(VAPID_PUBLIC_KEY),
        "private_key_exists": bool(VAPID_PRIVATE_KEY),
        "public_key_preview": VAPID_PUBLIC_KEY[:20] if VAPID_PUBLIC_KEY else None
    }

# ===================== RODAR =====================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)