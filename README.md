# NAVI

Assistente multimodal para triagem financeira e faturamento, com suporte a texto, imagens e áudio.

## Visão geral

O projeto é uma aplicação em Python com interface Streamlit para auxiliar a Squad 5 na análise de evidências financeiras e documentais. Ele processa entradas de:

- imagens de notas fiscais e documentos;
- áudios de gestores ou operadores;
- textos com perguntas e instruções;

e combina essas evidências com um agente de IA para responder perguntas sobre:

- itens do catálogo;
- valores e totais;
- validação de documentos (CPF/CNPJ);
- conferência de somas de notas;
- consultas ao banco local de clientes e faturamento;
- acompanhamento de risco e divergências.

Em outras palavras, o sistema não é apenas um chatbot genérico: ele atua como um assistente de apoio financeiro, com validação de dados e consulta a base local.

## Funcionalidades implementadas no código

O projeto atende, de fato, as seguintes funções:

- triagem multimodal de evidências de texto, imagem e áudio;
- extração de informações de notas e documentos;
- validação de códigos de produto no padrão `A123`;
- consulta de item no catálogo SQLite por código;
- cálculo de total em BRL a partir de quantidade e preço unitário;
- validação de CPF e CNPJ com dígitos verificadores;
- conferência de somas de itens x total da nota;
- descrição do schema do banco e execução de consultas SQL somente leitura;
- respostas baseadas em dados do banco de clientes, notas e faturamento;
- avaliação de risco e divergências de documentação;
- síntese e reprodução de resposta em voz (via texto para fala), quando disponível.

## Fluxo real da aplicação

A aplicação usa:

- `app.py` como interface principal em Streamlit;
- `src/core/agent.py` como agente central, com chamadas explícitas de ferramentas;
- `src/core/ingestion.py` para despachar texto/imagem/áudio para o processador correto;
- `src/vision/processor.py` para processamento de imagem;
- `src/audio/processor.py` para processamento de áudio;
- `src/tools/local.py` e `src/tools/dados.py` para acesso ao catálogo e ao banco local;
- `src/tools/validacao.py` para validações financeiras e documentais;
- `src/core/config.py` para configuração do cliente Gemini.

## Estrutura do projeto

```text
.
├── app.py
├── config.toml
├── requirements.txt
├── README.md
├── data/
├── src/
│   ├── audio/
│   ├── core/
│   ├── tools/
│   └── vision/
├── tests/
└── .env.example (se existir no ambiente local)
```

## Requisitos

- Python 3.11+
- pip
- chave de API Gemini em um arquivo `.env`
- biblioteca de áudio/vision compatível com o ambiente local

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

A interface principal do projeto é a Streamlit localizada em `app.py`:

```bash
streamlit run app.py
```

## Testes

```bash
python -m pytest
```

## Observações importantes

- O banco local é SQLite e fica em `data/catalogo.sqlite`.
- O projeto usa dados de demonstração para clientes, notas fiscais e itens.
- As consultas ao banco são tratadas como leitura somente, com validações e regras de segurança.
- O agente usa chamadas explícitas de ferramentas para evitar que a IA invente respostas ou execute operações não autorizadas.
- A validação de risco e a auditoria de divergência são parte do comportamento real da aplicação.

## Resumo em uma frase

O OmniAssistant é um assistente multimodal para triagem financeira, capaz de analisar notas fiscais, validar documentos, consultar catálogo e banco local, confirmar somas e responder com contexto e risco.
