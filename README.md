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

## Testes

```bash
python -m pytest
```

## Observações

- O projeto usa modelos e contratos centralizados em `src/core`.
- A lógica de ingestão e processamento multimodal está separada por módulos.
- O banco local SQLite fica em `data/catalogo.sqlite`.
