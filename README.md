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
- revisão e confirmação dos dados extraídos da conversa;
- exportação do histórico da conversa para CSV usando apenas Python;
- envio do resumo da análise por e-mail via SMTP.

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
- chave de API Gemini em um arquivo `.env`;
- credenciais SMTP, caso queira enviar e-mails;
- biblioteca de áudio/vision compatível com o ambiente local

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

O envio de e-mail usa o SMTP do Google. Ative a verificação em duas etapas na conta,
crie uma **senha de app** nas configurações da Conta Google e use essa senha, não a
senha normal da conta. Acrescente ao `.env`:

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=seu-email@gmail.com
SMTP_PASSWORD=sua_senha_de_app
SMTP_FROM=seu-email@gmail.com
```

Para contas Google Workspace, o administrador também pode exigir o uso do Gmail
SMTP Relay. Nesse caso, substitua o host e as regras de autenticação conforme a
política da organização.

O CSV é gerado diretamente em memória pelo módulo `src/core/exportacao.py`, a partir
das consultas ao banco feitas durante a conversa: cada resposta guarda o rastro das
ferramentas e as linhas retornadas por `consultar_banco` viram linhas do arquivo.
Assim, o CSV contém apenas os dados financeiros efetivamente consultados, sem a
conversa em si. O botão de exportação só aparece depois que há uma pergunta
analisada com resultados de consulta. Não é necessário configurar Google Cloud,
API key, conta de serviço ou qualquer credencial de planilha. O arquivo baixado
pode ser aberto no Excel ou importado manualmente no Google Sheets.

## Executando a aplicação

A interface principal do projeto é a Streamlit localizada em `app.py`:

```bash
streamlit run app.py
```

Depois de iniciar:

1. Envie uma imagem, áudio ou texto para análise.
2. Faça uma pergunta no chat.
3. Abra **Enviar dados da análise** na resposta.
4. Revise ou corrija os campos, informe o destinatário e confirme a revisão.
5. Se necessário, revise os dados e use **Enviar e-mail**.
6. Use **Exportar dados bancários (.csv)** para baixar as linhas retornadas pelas
   consultas ao banco desta conversa (clientes, notas, valores, status etc.;
   as colunas variam conforme a consulta). O botão só aparece depois de uma
   pergunta analisada com resultados de consulta.

Operações com risco `vermelho` são bloqueadas. Sem as credenciais correspondentes, a aplicação informa a configuração ausente e não simula sucesso.

## Testes

```bash
# Suíte completa
.venv/bin/python -m pytest

# Testes focados no e-mail e nos dados financeiros em CSV
.venv/bin/python -m pytest tests/test_finalizacao.py tests/test_exportacao.py
```

Os testes que chamam o Gemini ou processam áudio/imagem podem exigir API configurada, rede e modelos locais disponíveis. Os testes de finalização usam mocks e não enviam e-mails reais; os testes de CSV criam um banco temporário e validam os campos exportados.

Para verificar a conexão e a autenticação do Gmail SMTP sem enviar uma mensagem:

```bash
.venv/bin/python -c "import os, smtplib; from pathlib import Path; from dotenv import load_dotenv; load_dotenv(Path('.env')); s=smtplib.SMTP(os.getenv('SMTP_HOST', 'smtp.gmail.com'), int(os.getenv('SMTP_PORT', '587')), timeout=30); s.starttls(); s.login(os.environ['SMTP_USERNAME'], os.environ['SMTP_PASSWORD']); s.quit(); print('SMTP autenticado')"
```

Esse comando valida apenas TLS e login. O envio real ocorre pelo botão **Enviar
e-mail**, depois da confirmação dos dados e do destinatário.

## Observações importantes

- O banco local é SQLite e fica em `data/catalogo.sqlite`.
- O projeto usa dados de demonstração para clientes, notas fiscais e itens.
- As consultas ao banco são tratadas como leitura somente, com validações e regras de segurança.
- O agente usa chamadas explícitas de ferramentas para evitar que a IA invente respostas ou execute operações não autorizadas.
- A validação de risco e a auditoria de divergência são parte do comportamento real da aplicação.

## Resumo em uma frase

O OmniAssistant é um assistente multimodal para triagem financeira, capaz de analisar notas fiscais, validar documentos, consultar catálogo e banco local, confirmar somas e responder com contexto e risco.
