import os
from pathlib import Path
from tempfile import TemporaryDirectory
import streamlit as st
from src.core.contracts import EntradaUsuario, EvidenciaMultimodal
from src.core.ingestion import despachar_ingestao
from src.core.agent import executar_agente
from src.tools.local import inicializar_banco

# Configuracao da Pagina
st.set_page_config(page_title="OmniAssistant", layout="wide", initial_sidebar_state="expanded")

# Inicializa o banco SQLite local
inicializar_banco()

# Inicializacao do Estado da Sessao (Session State)
if "historico_mensagens" not in st.session_state:
    st.session_state["historico_mensagens"] = []
if "evidencias_ativas" not in st.session_state:
    st.session_state["evidencias_ativas"] = []

st.title("OmniAssistant: Assistente Multimodal Inteligente")
st.caption("Solucao desenvolvida pela Squad para analise integrada de imagens, audios de comando e consultas corporativas.")

# Barra Lateral: Uploads e Configuracoes
with st.sidebar:
    st.header("Entradas Multimodais")
    upload_img = st.file_uploader("Upload de Imagem (Print / Diagrama)", type=["png", "jpg", "jpeg"])
    upload_audio = st.file_uploader("Upload de Audio de Comando", type=["wav", "mp3", "ogg"])
    
    if st.button("Limpar Sessao e Cache"):
        st.session_state["historico_mensagens"].clear()
        st.session_state["evidencias_ativas"].clear()
        st.rerun()

# Processamento de Uploads com Cache
novas_evidencias = []
col_preview1, col_preview2 = st.columns(2)

if upload_img:
    with col_preview1:
        st.subheader("Preview da Imagem")
        st.image(upload_img, use_container_width=True)
        # Salva em arquivo temporario para ingestao
        with TemporaryDirectory() as tmp_dir:
            caminho_tmp = Path(tmp_dir) / upload_img.name
            caminho_tmp.write_bytes(upload_img.getvalue())
            try:
                ev_img = despachar_ingestao(EntradaUsuario(tipo="imagem", caminho_arquivo=caminho_tmp))
                novas_evidencias.append(ev_img)
            except Exception as e:
                st.error(f"Erro ao processar imagem: {e}")

if upload_audio:
    with col_preview2:
        st.subheader("Preview do Audio")
        st.audio(upload_audio)
        with TemporaryDirectory() as tmp_dir:
            caminho_tmp = Path(tmp_dir) / upload_audio.name
            caminho_tmp.write_bytes(upload_audio.getvalue())
            try:
                ev_audio = despachar_ingestao(EntradaUsuario(tipo="audio", caminho_arquivo=caminho_tmp))
                novas_evidencias.append(ev_audio)
                with st.expander("Transcricao Whisper"):
                    st.write(ev_audio.resumo_informacao)
            except Exception as e:
                st.error(f"Erro ao processar audio: {e}")

st.session_state["evidencias_ativas"] = novas_evidencias

# Exibicao do Historico de Chat
# Renderizacao Enriquecida com Painel XAI
for msg in st.session_state["historico_mensagens"]:
    with st.chat_message(msg["papel"]):
        st.write(msg["conteudo"])
        
        # Se for mensagem do assistente e contiver telemetria, exibe os detalhes
        telemetria = msg.get("telemetria")
        if telemetria:
            tempo_ms = telemetria.get("tempo_total_ms", 0)
            tokens = telemetria.get("tokens_estimados", "N/A")
            turnos = telemetria.get("total_turnos", 1)
            
            st.caption(f"Tempo de Execucao: {tempo_ms}ms | Turnos Agênticos: {turnos} | Tokens: {tokens}")
            
            rastro = telemetria.get("rastro_ferramentas", [])
            if rastro:
                with st.expander(f"Auditoria de Ferramentas ({len(rastro)} acoes executadas)"):
                    for idx, tool in enumerate(rastro, start=1):
                        st.markdown(f"**{idx}. Ferramenta:** `{tool['ferramenta']}` ({tool.get('duracao_ms', 0)}ms)")
                        st.json({"argumentos": tool["argumentos"], "resultado_banco": tool["resultado"]})

# Campo de Entrada de Mensagem
comando_chat = st.chat_input("Digite sua pergunta sobre as evidencias ou peca uma acao...")
if comando_chat:
    st.session_state["historico_mensagens"].append({"papel": "user", "conteudo": comando_chat})
    
    with st.spinner("OmniAssistant raciocinando e consultando ferramentas..."):
        try:
            resultado = executar_agente(comando_chat, st.session_state["evidencias_ativas"])
            st.session_state["historico_mensagens"].append({
                "papel": "assistant",
                "conteudo": resultado["resposta"],
                "telemetria": resultado
            })
        except Exception as e:
            st.session_state["historico_mensagens"].append({
                "papel": "assistant",
                "conteudo": f"Falha na execucao: {type(e).__name__} - {e}"
            })
    st.rerun()