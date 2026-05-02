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

class HombrewSpellRequest(BaseModel):
    name: str
    class_name: str


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
  "skills": {{"acrobatics": 7, "stealth": 10}},
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


# ===================== RODAR =====================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)