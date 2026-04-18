import os
import json
import fitz  # PyMuPDF
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
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
    allow_origins=["*"],  # em produção troque pelo domínio do frontend
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


# ===================== FUNÇÃO AUXILIAR GEMINI =====================
def gerar_json_com_gemini(prompt: str) -> dict:
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


# ===================== ENDPOINTS =====================

@app.post("/create-character")
async def create_character(req: CreateCharacterRequest):
    """Cria personagem do zero com IA e salva no Supabase"""
    prompt = f"""
    Você é um mestre experiente de RPG. Crie uma ficha completa e equilibrada.

    Sistema: {req.system}
    Descrição do jogador: {req.description}
    Contexto da campanha: {req.campaign_context or 'Nenhum'}

    Retorne APENAS um JSON válido com esta estrutura exata:
    {{
      "name": "Nome",
      "race": "...",
      "class": "...",
      "level": 1,
      "alignment": "...",
      "background": "...",
      "attributes": {{ "str": 10, "dex": 15, "con": 12, "int": 8, "wis": 13, "cha": 10 }},
      "skills": {{ "acrobatics": 5, "stealth": 3 }},
      "inventory": ["item1", "item2"],
      "features": ["feature1", "feature2"],
      "background_story": "História curta..."
    }}
    """
    try:
        ficha = gerar_json_com_gemini(prompt)

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
    except Exception as e:
        raise HTTPException(500, f"Erro na IA: {str(e)}")


@app.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...), system: str = "D&D 5e", user_id: str = "", campaign_id: str = ""):
    """Importa ficha PDF (D&D Beyond, Tormenta, etc.) e salva no Supabase"""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Arquivo deve ser PDF")

    contents = await file.read()

    if not contents:
        raise HTTPException(400, "PDF está vazio ou corrompido")

    doc = fitz.open(stream=contents, filetype="pdf")
    text = ""
    for page_num, page in enumerate(doc):
        text += f"\n--- PÁGINA {page_num + 1} ---\n"
        text += page.get_text("text")

    if not text.strip():
        raise HTTPException(400, "Não foi possível extrair texto do PDF")

    prompt = f"""
    Extraia TODOS os dados da ficha de RPG do texto abaixo.
    Sistema do jogo: {system}
    O texto pode ser de D&D Beyond 2024, Tormenta, Call of Cthulhu ou outro.

    Retorne APENAS um JSON com esta estrutura (preencha tudo que conseguir):
    {{
      "name": "...",
      "race": "...",
      "class": "...",
      "level": 1,
      "alignment": "...",
      "background": "...",
      "attributes": {{ "str": 10, "dex": 18, "con": 14, "int": 8, "wis": 16, "cha": 8 }},
      "skills": {{ "acrobatics": 7, "stealth": 9 }},
      "inventory": ["item1", "item2"],
      "features": ["Martial Arts", "Flurry of Blows"],
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


@app.get("/characters")
async def list_characters(user_id: str = "", campaign_id: str = ""):
    """Lista personagens, podendo filtrar por usuário ou campanha"""
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
    """Busca um personagem pelo ID"""
    try:
        response = supabase.table("characters").select("*").eq("id", character_id).single().execute()
        if not response.data:
            raise HTTPException(404, "Personagem não encontrado")
        return {"success": True, "data": response.data}
    except Exception as e:
        raise HTTPException(500, f"Erro ao buscar personagem: {str(e)}")


@app.delete("/characters/{character_id}")
async def delete_character(character_id: str):
    """Deleta um personagem pelo ID"""
    try:
        supabase.table("characters").delete().eq("id", character_id).execute()
        return {"success": True, "message": "Personagem deletado"}
    except Exception as e:
        raise HTTPException(500, f"Erro ao deletar personagem: {str(e)}")


@app.post("/npcs")
async def create_npc(campaign_id: str, description: str, system: str = "D&D 5e"):
    """Cria NPC com IA e salva no Supabase"""
    prompt = f"""
    Você é um mestre experiente de RPG. Crie um NPC interessante e detalhado.

    Sistema: {system}
    Descrição: {description}

    Retorne APENAS um JSON válido:
    {{
      "name": "...",
      "race": "...",
      "occupation": "...",
      "personality": "...",
      "secret": "...",
      "appearance": "...",
      "motivation": "...",
      "attributes": {{ "str": 10, "dex": 10, "con": 10, "int": 10, "wis": 10, "cha": 10 }},
      "notes": "..."
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
            "saved_id": response.data[0]["id"] if response.data else None
        }
    except Exception as e:
        raise HTTPException(500, f"Erro ao criar NPC: {str(e)}")


@app.get("/npcs/{campaign_id}")
async def list_npcs(campaign_id: str):
    """Lista NPCs de uma campanha"""
    try:
        response = supabase.table("npcs").select("*").eq("campaign_id", campaign_id).execute()
        return {"success": True, "data": response.data}
    except Exception as e:
        raise HTTPException(500, f"Erro ao buscar NPCs: {str(e)}")


@app.get("/skill-description/{skill_name}")
async def get_skill_description(skill_name: str, system: str = "D&D 5e", character_context: str = ""):
    """Retorna descrição de uma habilidade via IA"""
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


@app.get("/")
async def root():
    return {"status": "RPG IA Backend rodando!", "version": "1.0"}


# ===================== RODAR =====================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)