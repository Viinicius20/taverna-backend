# ⚔ Taverna RPG — Backend

[![CI](https://github.com/Viinicius20/taverna-backend/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Viinicius20/taverna-backend/actions/workflows/ci.yml)

> API REST em FastAPI da plataforma Taverna RPG: fichas de D&D 5e, painel do mestre e um "mundo vivo" (eventos, economia, viagens, segredos), com conteúdo gerado por IA. Projeto pessoal, em uso na minha mesa de D&D.

🔗 **App:** [taverna-frontend.vercel.app](https://taverna-frontend.vercel.app) · **Frontend:** [github.com/Viinicius20/taverna-frontend](https://github.com/Viinicius20/taverna-frontend) · **API (Swagger):** [/docs](https://taverna-backend-eq3b.onrender.com/docs)

---

## ✦ O que faz

- **Jogadores:** ficha editável (multiclasse, subclasses, magias, inventário, perícias), criação por descrição ou importação de PDF, level up e aumento de atributo, diário, documentos recebidos, wiki da campanha, downtime entre sessões e sussurros do mestre com notificação push.
- **Mestre:** painel de combate, tela de TV de leitura (mapa, iniciativa e documentos revelados), mapa com tokens, geradores com IA (NPCs, locais, facções, encontros, loot, bestiário, documentos).
- **Mundo Vivo:** eventos com relógios de progresso, consequências ocultas, reputação de NPCs e facções, economia regional (eventos que alteram preços), viagens com eventos de estrada, gazeta com rascunho e publicação, e fatos que cada personagem ou NPC conhece.

---

## 🛠 Stack

| Camada | Tecnologia |
|--------|-----------|
| Framework | FastAPI (Python), Pydantic, slowapi (rate limit) |
| Banco de dados | Supabase (PostgreSQL com JSONB) |
| Storage | Supabase Storage |
| IA | Google Gemini 2.5 Flash, com rotação de chaves |
| Autenticação | JWT (PyJWT) e bcrypt |
| Notificações | Web Push API (VAPID) |
| Qualidade | pytest e GitHub Actions |
| Deploy | Docker e Render |

---

## 🧭 Decisões técnicas

- **Rotação de chaves do Gemini.** A cota gratuita é por projeto, então o `ia.py` percorre várias chaves, repete em caso de erro 503 e põe de lado uma chave que estourou a cota (1 hora se for a cota diária, 1 minuto se for por minuto).
- **Autorização por papel.** O mestre entra com senha (hash bcrypt) e recebe um JWT. Rotas de escrita e as que devolvem segredos usam a dependência `exigir_mestre`. Jogadores entram só com o apelido.
- **Segredos ficam no servidor.** Os endpoints dos jogadores selecionam só as colunas públicas: as notas do mestre na wiki nunca saem da API, e a tela de TV mostra o HP dos monstros como estado (ileso, ferido, crítico) em vez de número.
- **Refatoração guiada por testes.** O `main.py` era um arquivo único de cerca de 3.800 linhas. Dividi em routers com um script que usa `ast` para mover rotas sem mudar nenhuma URL, e os testes garantem que nenhuma rota perdeu a proteção no caminho.

---

## ✦ Rotas

São mais de 170 rotas, então a lista completa e sempre atualizada fica na documentação interativa em [`/docs`](https://taverna-backend-eq3b.onrender.com/docs). Resumo por área:

| Área | Prefixos |
|------|----------|
| Personagens | `/characters`, `/create-character`, `/upload-pdf`, `/level-up`, `/aplicar-asi`, `/diario` |
| NPCs e segredos | `/npcs`, `/secret-stages` |
| Ferramentas do mestre | `/encounter`, `/loot`, `/rules`, `/bestiary`, `/magic-items`, `/spells` |
| Mapa, galeria e TV | `/map-tokens`, `/gallery`, `/combat`, `/tv` |
| Mundo Vivo | `/world-events`, `/world-log`, `/world-changelog`, `/flags`, `/prophecies`, `/presagios`, `/consequencias` |
| Mundo físico | `/factions`, `/locations`, `/reputation` |
| Campanha | `/economia`, `/viagem`, `/gazeta`, `/downtime`, `/misterios`, `/notas-sessao`, `/arquivo-mestre`, `/wiki`, `/fatos-mundo` |
| Contas e avisos | `/profiles/login`, `/secret-messages`, `/push`, `/notify` |
| Campanhas (código de convite) | `/campaigns` |

---

## ⚙ Variáveis de Ambiente

O arquivo `.env.example` tem os nomes de todas elas.

```env
SUPABASE_URL=
SUPABASE_KEY=
JWT_SECRET=          
GEMINI_API_KEY=
GEMINI_API_KEY_2=
GEMINI_API_KEY_3=
GEMINI_API_KEY_4=
VAPID_PUBLIC_KEY=
VAPID_PRIVATE_KEY=
```

---

## 🚀 Rodando Localmente

```bash
# Criar ambiente virtual
python -m venv venv
venv\Scripts\activate          # Linux/macOS: source venv/bin/activate

# Instalar dependências
pip install -r requirements.txt

# Iniciar servidor (documentação em http://localhost:8000/docs)
uvicorn main:app --reload
```

A senha do mestre é definida com `python definir_senha.py`.

Com Docker (ajuste a porta conforme o seu `Dockerfile`):

```bash
docker build -t taverna-backend .
docker run --env-file .env -p 8000:8000 taverna-backend
```

---

## 🧪 Testes e CI

Os testes cobrem as regras puras e a proteção das rotas: toda rota do mestre responde `401` sem token e `403` com token de jogador, e as rotas dos jogadores continuam abertas. O GitHub Actions roda o `pytest` a cada push.

```bash
python -m pytest -q
```

---

## 📁 Estrutura do Projeto

```
backend/
├── main.py              # App FastAPI, CORS, rate limit e rotas ainda não extraídas
├── core.py              # Cliente do Supabase e configuração
├── auth.py              # JWT, hash de senha e dependências de autorização
├── ia.py                # Chamadas ao Gemini (rotação de chaves, retry, pausa por cota)
├── servicos.py          # Regras de negócio compartilhadas entre rotas
├── utils.py             # Funções puras
├── routers/             # Rotas por assunto
├── test/                # Testes com pytest
├── Dockerfile
├── requirements.txt     # Dependências Python
├── .env.example         # Variáveis de ambiente necessárias
└── .gitignore
```

---

## ⚠ Limitações conhecidas

- Uso pessoal: uma campanha por vez (o id é fixo no código).
- Jogadores entram só com o apelido, sem senha, então quem souber o apelido de outro jogador consegue entrar como ele. O mestre tem senha.
- O RLS do Supabase está desligado; a autorização é feita na API.
- As rotas de IA dependem da cota gratuita do Gemini.

---

## 🔗 Repositório do Frontend

[github.com/Viinicius20/taverna-frontend](https://github.com/Viinicius20/taverna-frontend)