import os
import json
import fitz  # PyMuPDF
from google.genai.errors import ServerError
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from pydantic import BaseModel
from supabase import create_client, Client
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

# ===================== CONFIG =====================
app = FastAPI(title="RPG IA - Backend")

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


# ===================== FUNÇÃO AUXILIAR GEMINI =====================
from google.genai.errors import ServerError
import time

def gerar_json_com_gemini(prompt: str, max_retries=3) -> dict:
    last_error = None

    for tentativa in range(max_retries):
        try:
            response = client.models.generate_content(
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

        except ServerError as e:
            last_error = e
            print(f"[IA] 503 tentativa {tentativa+1}/{max_retries}")
            time.sleep(2 * (tentativa + 1))  # backoff progressivo

        except json.JSONDecodeError as e:
            print("[IA] JSON inválido, tentando corrigir...")
            try:
                # tentativa simples de correção
                text = text.split("```")[-1]
                return json.loads(text)
            except:
                last_error = e

        except Exception as e:
            last_error = e
            break

    raise last_error


# ===================== ENDPOINTS =====================

@app.post("/create-character")
async def create_character(req: CreateCharacterRequest):
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
        ficha = gerar_json_com_gemini(prompt)
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
        update_data = {"data": req.data}
        if req.name:
            update_data["name"] = req.name
        if req.system:
            update_data["system"] = req.system
        response = supabase.table("characters").update(update_data).eq("id", character_id).execute()
        return {"success": True, "data": response.data}
    except Exception as e:
        raise HTTPException(500, f"Erro ao atualizar personagem: {str(e)}")


@app.post("/level-up")
async def level_up(req: LevelUpRequest):
    ficha = req.ficha_atual
    nivel_atual = ficha.get("level", 1)

    if req.nivel_alvo <= nivel_atual:
        raise HTTPException(400, "Nível alvo deve ser maior que o nível atual")
    if req.nivel_alvo > 20:
        raise HTTPException(400, "Nível máximo é 20")

        class_name_alvo = getattr(req, 'class_name', None)

        if isinstance(ficha.get("classes"), list) and len(ficha["classes"]) > 1:
            if not class_name_alvo:
                raise HTTPException(400, {
                    "error": "Escolha qual classe fazer level up",
                    "classes": [{"name": c["name"], "level": c["level"]} for c in ficha["classes"]]
                })

            classe_encontrada = next(
                (c for c in ficha["classes"] if c["name"].lower() == class_name_alvo.lower()),
                None
            )
            if not classe_encontrada:
                raise HTTPException(400, f"Classe '{class_name_alvo}' não encontrada")

            classe_encontrada["level"] += 1
            ficha["total_level"] = sum(c.get("level", 1) for c in ficha["classes"])
        else:
            # Se tem só 1 classe, incrementa ela automaticamente
            if isinstance(ficha.get("classes"), list) and len(ficha["classes"]) == 1:
                ficha["classes"][0]["level"] += 1
                ficha["total_level"] = ficha["classes"][0]["level"]

    prompt = f"""
    Você é um mestre experiente de RPG. Um personagem subiu de nível.

    Sistema: {req.system}
    Nome: {ficha.get("name")}
    Raça: {ficha.get("race")}
    Classes: {json.dumps(ficha.get("classes", [{"name": ficha.get("class")}]))}
    Nível atual: {nivel_atual}
    Nível alvo: {req.nivel_alvo}
    Features atuais: {json.dumps(ficha.get("features", []))}
    Atributos atuais: {json.dumps(ficha.get("attributes", {}))}
    Combat atual: {json.dumps(ficha.get("combat", {}))}

    Atualize a ficha para o nível {req.nivel_alvo}. Recalcule os stats de combate para o novo nível.

    Retorne APENAS um JSON válido com a ficha COMPLETA atualizada:
    {{
      "name": "{ficha.get("name")}",
      "race": "{ficha.get("race")}",
      "class": "{ficha.get("class")}",
      "level": {req.nivel_alvo},
      "alignment": "{ficha.get("alignment")}",
      "background": "{ficha.get("background")}",
      "attributes": {{ "str": 10, "dex": 15, ... }},
      "combat": {{
        "hp": 0,
        "hp_max": 0,
        "ac": 0,
        "initiative": 0,
        "speed": 30,
        "proficiency_bonus": 0,
        "passive_perception": 0,
        "saving_throws": {{ "str": 0, "dex": 0, "con": 0, "int": 0, "wis": 0, "cha": 0 }},
        "hit_dice": "1d8"
      }},
      "skills": {{ "acrobatics": 5, ... }},
      "inventory": [...],
      "features": [...todas as features antigas + novas...],
      "background_story": "..."
    }}
    """
    try:
        ficha_nova = gerar_json_com_gemini(prompt)
        supabase.table("characters").update({
            "data": ficha_nova,
            "name": ficha_nova.get("name", ficha.get("name"))
        }).eq("id", req.character_id).execute()
        return {"success": True, "data": ficha_nova}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, "Erro ao processar level up")

def extrair_texto_pdf(contents):
    """Extrai texto de um PDF"""
    try:
        import PyPDF2
        from io import BytesIO

        pdf_file = BytesIO(contents)
        pdf_reader = PyPDF2.PdfReader(pdf_file)

        text = ""
        for page in pdf_reader.pages:
                text += page.extract_text()

        return text
    except Exception as e:
        return f"Erro ao extrair PDF: {str(e)}"


@app.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...), system: str = "D&D 5e", user_id: str = "", campaign_id: str = ""):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Arquivo deve ser PDF")

    contents = await file.read()
    if not contents:
        raise HTTPException(400, "PDF está vazio ou corrompido")

    text = extrair_texto_pdf(contents)
    if not text.strip():
        raise HTTPException(400, "Não foi possível extrair texto do PDF")

    prompt = f"""
    Extraia TODOS os dados da ficha de RPG do texto abaixo.
    Sistema do jogo: {system}

    Retorne APENAS um JSON com esta estrutura:
    {{
      "name": "...",
      "race": "...",
      "class": "...",
      "level": 1,
      "alignment": "...",
      "background": "...",
      "attributes": {{ "str": 10, "dex": 18, "con": 14, "int": 8, "wis": 16, "cha": 8 }},
      "combat": {{
        "hp": 0,
        "hp_max": 0,
        "ac": 0,
        "initiative": 0,
        "speed": 30,
        "proficiency_bonus": 2,
        "passive_perception": 0,
        "saving_throws": {{ "str": 0, "dex": 0, "con": 0, "int": 0, "wis": 0, "cha": 0 }},
        "hit_dice": "1d8"
      }},
      "skills": {{ "acrobatics": 7, "stealth": 9 }},
      "inventory": ["item1", "item2"],
      "features": ["feature1", "feature2"],
       "spellcasting": {{
        "ability": "int",
        "dc": 0,
        "spells": []
      "background_story": "..."
    }}

    Texto da ficha:
    {text[:25000]}
    """

    try:
        ficha = gerar_json_com_gemini(prompt)
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
        raise HTTPException(500, f"Erro ao processar PDF: {str(e)}")


@app.post("/upload-pdf-npc")
async def upload_pdf_npc(file: UploadFile = File(...), system: str = "D&D 5e", campaign_id: str = ""):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Arquivo deve ser PDF")

    contents = await file.read()
    if not contents:
        raise HTTPException(400, "PDF está vazio ou corrompido")

    print("DEBUG: Chamando extrair_texto_pdf...")

    text = extrair_texto_pdf(contents)

    print(f"DEBUG: Texto extraído: {text[:100]}...")

    if not text.strip():
        raise HTTPException(400, "Não foi possível extrair texto do PDF")

    prompt = f"""
       Extraia TODOS os dados da ficha de RPG do texto abaixo e organize como NPC.
       Sistema do jogo: {system}

       Retorne APENAS um JSON com esta estrutura:
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
         "attributes": {{ "str": 10, "dex": 18, "con": 14, "int": 8, "wis": 16, "cha": 8 }},
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

    Texto da ficha:
    {text[:25000]}
    """
    try:
        dados = gerar_json_com_gemini(prompt)
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
        raise HTTPException(500, f"Erro ao processar PDF: {str(e)}")

@app.get("/characters")
async def list_characters(user_id: str = "", campaign_id: str = ""):
    try:
        query = supabase.table("characters").select("*")
        if user_id:
            query = query.eq("user_id", user_id)
        if campaign_id:
            query = query.eq("campaign_id", campaign_id)
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


@app.post("/npcs")
async def create_npc(campaign_id: str, description: str, system: str = "D&D 5e"):
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

    # ======================= SPELLS =======================

SPELLS_BY_CLASS = {
    "Wizard": [
        {"name": "Fire Bolt", "level": 0},
        {"name": "Ray of Frost", "level": 0},
        {"name": "Minor Illusion", "level": 0},
        {"name": "Prestidigitation", "level": 0},
        {"name": "Mending", "level": 0},
        {"name": "Shocking Grasp", "level": 0},
        {"name": "Magic Missile", "level": 1},
        {"name": "Shield", "level": 1},
        {"name": "Mage Armor", "level": 1},
        {"name": "Fireball", "level": 3},
        {"name": "Ice Storm", "level": 4},
        {"name": "Cone of Cold", "level": 5},
    ],
    "Mago": [
        {"name": "Disparo de Fogo", "level": 0},
        {"name": "Bola de Fogo", "level": 3},
        {"name": "Míssil Mágico", "level": 1},
        {"name": "Armadura Mágica", "level": 1},
    ],
    "Cleric": [
        {"name": "Light", "level": 0},
        {"name": "Sacred Flame", "level": 0},
        {"name": "Guidance", "level": 0},
        {"name": "Cure Wounds", "level": 1},
        {"name": "Healing Word", "level": 1},
        {"name": "Spiritual Weapon", "level": 2},
        {"name": "Revivify", "level": 3},
    ],
    "Sacerdote": [
        {"name": "Curar Ferimentos", "level": 1},
        {"name": "Palavra de Cura", "level": 1},
        {"name": "Arma Espiritual", "level": 2},
    ],
    "Warlock": [
        {"name": "Eldritch Blast", "level": 0},
        {"name": "Agonizing Blast", "level": 0},
        {"name": "Hex", "level": 1},
        {"name": "Armor of Agathys", "level": 1},
        {"name": "Darkness", "level": 2},
    ],
    "Bruxo": [
        {"name": "Explosão Sobrenatural", "level": 0},
        {"name": "Maldição", "level": 1},
    ]
}

@app.get("/spells")
async def get_spells(class_name: str = "Wizard"):
        spells = SPELLS_BY_CLASS.get(class_name, [])
        return {"success": True, "data": spells}


@app.get("/")
async def root():
    return {"status": "RPG IA Backend rodando!", "version": "1.0"}


# ===================== RODAR =====================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)