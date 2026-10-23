# NAVI

Assistente multimodal para triagem financeira e faturamento, com suporte a texto, imagem, áudio, consulta ao banco local e envio de resumo por e-mail.

## Visão geral

O NAVI é uma aplicação em Python com interface Streamlit para apoiar a análise de evidências financeiras e documentais. Ele processa entradas de:

- imagens de notas fiscais, documentos e prints;
- arquivos de áudio com comando do gestor ou operador;
- texto com perguntas e instruções;
- consultas ao banco local de clientes, notas e faturamento.

O sistema combina essas evidências com um agente baseado em IA e ferramentas explícitas para responder perguntas sobre:

- itens do catálogo;
- valores e totais;
- validação de CPF/CNPJ;
- conferência de somas de notas fiscais;
- clientes, notas e faturamento no SQLite;
- risco e divergências detectadas na análise;
- resumo em voz da resposta final;
- revisão final e envio por e-mail do resultado.

## Funcionalidades implementadas no código

O projeto atende, de fato, as seguintes funções:

- triagem multimodal de texto, imagem e áudio;
- múltiplos uploads de imagens e áudios na mesma sessão;
- processamento de imagem com extração textual/visual;
- transcrição de áudio usando Whisper;
- validação de códigos de produto no padrão `A123`;
- consulta de item no catálogo por código;
- cálculo de total em BRL a partir de quantidade e preço unitário;
- validação de CPF e CNPJ com dígitos verificadores;
- conferência de soma dos itens contra o total da nota;
- descrição do esquema do banco e execução de consultas SQL somente leitura;
- respostas baseadas em dados de clientes, notas e faturamento;
- avaliação de risco e alertas de divergência;
- geração de resposta por voz;
- revisão dos dados antes do envio;
- exportação dos dados financeiros consultados em CSV;
- envio do resumo por e-mail via SMTP.

## Fluxo real da aplicação

A aplicação usa:

- `app.py` como interface principal em Streamlit;
- `src/core/agent.py` como agente central com ferramentas explícitas;
- `src/core/ingestion.py` para despachar texto, imagem e áudio;
- `src/vision/processor.py` para processamento de imagem;
- `src/audio/processor.py` para processamento de áudio;
- `src/tools/local.py` para o catálogo de itens;
- `src/tools/dados.py` para o banco de clientes e notas de exemplo;
- `src/tools/validacao.py` para validações financeiras e documentais;
- `src/core/config.py` para configuração do cliente Gemini;
- `src/core/finalizacao.py` e `src/integrations/email.py` para revisão e envio por e-mail.

## Estrutura do projeto

```text
.
├── app.py
├── README.md
├── requirements.txt
├── config.toml
├── .env
├── data/
│   └── catalogo.sqlite
├── src/
│   ├── audio/
│   ├── core/
│   ├── integrations/
│   ├── tools/
│   └── vision/
├── tests/
└── .venv/
```

## Requisitos

- Python 3.11+
- pip
- chave de API Gemini no arquivo `.env`
- credenciais SMTP para envio de e-mail, se quiser usar essa funcionalidade
- ambiente com suporte a áudio/vision local

## Instalação

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Variáveis de ambiente

Crie um arquivo `.env` na raiz do projeto com:

```env
GEMINI_API_KEY=sua_chave_aqui
```

Para o envio de e-mail, o projeto usa SMTP. Exemplo para Gmail:

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=seu-email@gmail.com
SMTP_PASSWORD=sua_senha_de_app
SMTP_FROM=seu-email@gmail.com
```

Importante:
- para Gmail, normalmente é necessário usar uma senha de app;
- não use a senha principal da conta;
- ative a verificação em duas etapas primeiro.

## Executando a aplicação

```bash
streamlit run app.py
```

Depois de iniciar:

1. envie uma ou mais imagens e/ou áudios;
2. faça uma pergunta no chat;
3. revise a análise e use a seção de envio;
4. exporte os dados financeiros em CSV quando houver consulta ao banco;
5. envie por e-mail se o destinatário e as credenciais SMTP estiverem configurados.

## Banco de dados local

O banco é SQLite e fica em:

```text
data/catalogo.sqlite
```

Ele contém dados de demonstração para:

- `itens` (catálogo de produtos/serviços)
- `clientes` (empresas/fornecedores)
- `notas_fiscais` (notas emitidas)
- `notas_itens` (itens de cada nota)

Para recriar os dados de exemplo, você pode usar as funções de `src/tools/dados.py`:

```bash
python - <<'PY'
from src.tools.dados import reiniciar_dados
reiniciar_dados()
print('Banco resetado e recarregado')
PY
```

## Testes

```bash
python -m pytest
```

Se quiser validar funções específicas de e-mail e exportação:

```bash
python -m pytest tests/test_finalizacao.py
python -m pytest tests/test_exportacao.py
```

## Observações importantes

- O banco local é SQLite e fica em `data/catalogo.sqlite`.
- O projeto usa dados sintéticos para demonstração e testes.
- As consultas ao banco são tratadas como leitura somente, com validações e regras de segurança.
- O agente usa ferramentas explícitas para reduzir invento de informações.
- A validação de risco e a auditoria de divergência são parte do comportamento real da aplicação.
- Operações com risco grave podem ser bloqueadas antes do envio final.

## Resumo em uma frase

O NAVI é um assistente multimodal para triagem financeira e faturamento, capaz de analisar notas fiscais, validar documentos, consultar catálogo e banco local, confirmar somas, exportar dados e enviar a análise por e-mail com contexto e risco.
