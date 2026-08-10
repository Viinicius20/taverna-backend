# ⚔ Taverna RPG — Backend

> API REST em FastAPI para a plataforma Taverna RPG.

🔗 **[taverna-frontend.vercel.app](https://taverna-frontend.vercel.app)**

---

## 🛠 Stack

| Camada | Tecnologia |
|--------|-----------|
| Framework | FastAPI (Python) |
| Banco de dados | Supabase (PostgreSQL) |
| Storage | Supabase Storage |
| IA | Google Gemini 2.5 Flash |
| Notificações | Web Push API (VAPID) |
| Deploy | Render |

---

## ✦ Endpoints

### Personagens
| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/characters` | Lista personagens |
| GET | `/characters/:id` | Busca personagem por ID |
| POST | `/create-character` | Cria personagem via IA |
| POST | `/upload-pdf` | Importa ficha de PDF |
| PUT | `/characters/:id` | Atualiza ficha |
| PATCH | `/characters/:id` | Atualiza campo específico |
| DELETE | `/characters/:id` | Deleta personagem |
| POST | `/level-up` | Sobe de nível via IA |
| POST | `/characters/:id/avatar` | Upload de foto de perfil |

### NPCs
| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/npcs/:campaign_id` | Lista NPCs da campanha |
| POST | `/npcs` | Gera NPC via IA |
| POST | `/upload-pdf-npc` | Importa NPC via PDF |
| DELETE | `/npcs/:id` | Deleta NPC |

### Mestre
| Método | Rota | Descrição |
|--------|------|-----------|
| POST | `/loot/generate` | Gera loot por nível |
| POST | `/rules/search` | Consulta regra via IA |
| POST | `/encounter/generate` | Gera encontro aleatório |
| GET | `/magic-items` | Lista itens mágicos |
| POST | `/magic-items/homebrew` | Cria item via IA |
| GET | `/bestiary` | Lista monstros |
| POST | `/bestiary/generate` | Gera monstro via IA |
| GET | `/arquetipos/:class_name` | Lista arquétipos por classe |
| GET | `/skill-description/:skill` | Descrição de habilidade via IA |

### Battle Map
| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/map-tokens/:campaign_id` | Lista tokens no mapa |
| POST | `/map-tokens` | Adiciona token ao mapa |
| PATCH | `/map-tokens/:id/position` | Atualiza posição |
| PATCH | `/map-tokens/:id/rotation` | Atualiza rotação |
| PATCH | `/map-tokens/:id/scale` | Atualiza escala |
| DELETE | `/map-tokens/:id` | Remove token |

### Galeria
| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/gallery` | Lista imagens |
| POST | `/gallery/upload` | Faz upload de imagem |
| PATCH | `/gallery/:id/reveal` | Revela imagem para jogadores |
| PATCH | `/gallery/:id/hide` | Esconde imagem |
| DELETE | `/gallery/:id` | Deleta imagem |

### Campanhas
| Método | Rota | Descrição |
|--------|------|-----------|
| POST | `/campaigns` | Cria campanha |
| GET | `/campaigns/:id` | Busca campanha por ID |
| GET | `/campaigns/by-owner/:owner_id` | Lista campanhas do mestre |
| POST | `/campaigns/join` | Entra em campanha por código |
| GET | `/campaigns/members/:campaign_id` | Lista membros da campanha |

### Notificações Push
| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/push/vapid-public-key` | Retorna chave pública VAPID |
| POST | `/push/subscribe` | Salva assinatura do dispositivo |
| POST | `/notify/item` | Notifica jogador de item recebido |

### Autenticação e Mensagens
| Método | Rota | Descrição |
|--------|------|-----------|
| POST | `/profiles/login` | Login leve por apelido |
| POST | `/secret-messages` | Envia mensagem secreta |
| GET | `/secret-messages/:character_id` | Busca mensagens não lidas |
| PATCH | `/secret-messages/:id/lida` | Marca mensagem como lida |

---

## ⚙ Variáveis de Ambiente

```env
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_anon_key
GEMINI_API_KEY=your_gemini_key
GEMINI_API_KEY_2=optional_fallback_key
GEMINI_API_KEY_3=optional_fallback_key
VAPID_PUBLIC_KEY=your_vapid_public_key
VAPID_PRIVATE_KEY=your_vapid_private_key
```

---

## 🚀 Rodando Localmente

```bash
# Criar ambiente virtual
python -m venv venv
venv\Scripts\activate   

# Instalar dependências
pip install -r requirements.txt

# Iniciar servidor
uvicorn main:app --reload
```

---

## 📁 Estrutura do Projeto

```
backend/
├── main.py              # Aplicação principal (endpoints)
├── requirements.txt     # Dependências Python
├── .env.example         # Variáveis de ambiente necessárias
└── .gitignore
```

---

## 🔗 Repositório do Frontend

[github.com/Viinicius20/taverna-frontend](https://github.com/Viinicius20/taverna-frontend)
