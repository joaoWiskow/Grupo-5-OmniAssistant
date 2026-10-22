# OmniAssistant

Assistente multimodal para triagem financeira e faturamento, com suporte a imagens, áudio e texto.

## Objetivo

O projeto foi desenvolvido para auxiliar a Squad 5 no processamento de evidências multimodais, como:
- imagens de notas fiscais e documentos;
- áudios de comando de gestores;
- consultas em texto para apoio à decisão.

## Estrutura do projeto

```text
.
├── app.py
├── requirements.txt
├── .env
├── data/
├── src/
│   ├── audio/
│   ├── core/
│   ├── tools/
│   └── vision/
├── tests/
└── README.md
```

## Requisitos

- Python 3.11+
- pip
- chave de API Gemini no arquivo `.env`

## Instalação

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Variável de ambiente

Crie um arquivo `.env` na raiz do projeto com:

```env
GEMINI_API_KEY=sua_chave_aqui
```

## Executando a aplicação

```bash
streamlit run app.py
```

## LLM tributário no Colab (GPU)

Dúvidas de finanças e tributação brasileiras são respondidas por
`rwayz/tributario-llama-8b-v2` (Llama-3.1-8B-Instruct com fine-tune pt-BR, 4-bit) rodando
no Colab e servido como API via `cloudflared`. Todo o chat passa por ele: o modelo recebe
as evidências e chama as próprias ferramentas (catálogo, banco, validações e cálculos).
O Gemini fica só com mídia: extrair texto de imagens e gerar voz.

1. Abra `notebooks/OmniFinance_Tributario.ipynb` no Colab com runtime **T4 GPU**.
2. Rode as células em ordem e copie a linha `COLAB_LLM_URL=...` para o `.env`.
3. Teste o túnel, o modelo e a chamada do agente: `python scripts/testar_colab.py`

O modelo é público, não precisa de token do Hugging Face. A URL expira quando a sessão do
Colab cai (~90 min ocioso, 12 h no total). Sem ela, o agente responde normalmente e a
ferramenta `consultar_especialista_financeiro` devolve erro.

## Autenticação e permissões

Os usuários ficam na tabela `usuarios` de `data/catalogo.sqlite` (seed automático na
primeira execução). Contas de demonstração:

| E-mail | Papel | Senha |
|---|---|---|
| admin@omni.ia | ADMIN | Admin@Master2026 |
| gestor@omni.ia | GESTOR | Gestor@Master2026 |
| analista@omni.ia | ANALISTA | Analista@Master2026 |
| auditor@omni.ia | AUDITOR | Auditor@Master2026 |

O chat só é liberado após o login. As ferramentas passam por
`despachar_tool_autenticado`, com RBAC por papel e trilha de auditoria.
`AUTH_ENFORCE=0` desliga o enforcement (apenas para desenvolvimento).
A tabela `usuarios` nunca é exposta às ferramentas SQL; `clientes` é oculta para ANALISTA.

Se o notebook do Colab exigir token, defina `COLAB_AUTH_TOKEN` no `.env`; ele vai no
cabeçalho `Authorization: Bearer` das chamadas ao `/chat`.

## Testes

```bash
python -m pytest
```

## Observações

- O projeto usa modelos e contratos centralizados em `src/core`.
- A lógica de ingestão e processamento multimodal está separada por módulos.
- O banco local SQLite fica em `data/catalogo.sqlite`.
