import os
import json
import time
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

MODELO = "gemini-2.5-flash"

GEMINI_KEYS = [
    os.getenv("GEMINI_API_KEY"),
    os.getenv("GEMINI_API_KEY_3"),
    os.getenv("GEMINI_API_KEY_2"),
    os.getenv("GEMINI_API_KEY_4"),
]

_esgotadas = {}   # key -> momento até o qual ela é pulada


def _chaves_disponiveis():
    agora = time.time()
    ativas = [k for k in GEMINI_KEYS if k and _esgotadas.get(k, 0) <= agora]
    return ativas or [k for k in GEMINI_KEYS if k]   # se todas estão em pausa, tenta mesmo assim


def _marcar_esgotada(key, erro):
    _esgotadas[key] = time.time() + (3600 if "PerDay" in str(erro) else 60)


def _chamar(contents, config=None, max_retries=3):
    ultimo_erro = None
    for idx, key in enumerate(_chaves_disponiveis()):
        client_atual = genai.Client(api_key=key)
        for tentativa in range(max_retries):
            try:
                return client_atual.models.generate_content(model=MODELO, contents=contents, config=config)
            except Exception as e:
                msg = str(e)
                ultimo_erro = e
                if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                    print(f"[IA] Key {idx+1}: quota esgotada, indo pra próxima...")
                    _marcar_esgotada(key, e)
                    break
                if "503" in msg or "UNAVAILABLE" in msg:
                    print(f"[IA] Key {idx+1}: 503 (tentativa {tentativa+1}/{max_retries})")
                    time.sleep(2 * (tentativa + 1))
                    continue
                print(f"[IA] Key {idx+1}: erro não tratado — {msg[:200]}")
                break
    raise ultimo_erro or RuntimeError("Nenhuma chave do Gemini configurada")


def gerar_texto_com_gemini(parts_ou_prompt, max_retries=3, json_mode=True):
    if isinstance(parts_ou_prompt, list):
        contents = [{"role": "user", "parts": parts_ou_prompt}]
        config = None
    else:
        contents = parts_ou_prompt
        config = types.GenerateContentConfig(
            temperature=0.7,
            **({"response_mime_type": "application/json"} if json_mode else {}),
        )
    return _chamar(contents, config, max_retries).text.strip()


def gerar_json_com_gemini(prompt: str, max_retries=3) -> dict:
    config = types.GenerateContentConfig(temperature=0.7, response_mime_type="application/json")
    text = _chamar(prompt, config, max_retries).text.strip()
    if text.startswith("```json"):
        text = text[7:-3].strip()
    return json.loads(text)