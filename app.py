from pathlib import Path
from tempfile import TemporaryDirectory
import streamlit as st
from src.core.contracts import EntradaUsuario, EvidenciaMultimodal
from src.core.ingestion import despachar_ingestao
from src.core.agent import executar_agente
from src.tools.local import inicializar_banco

st.set_page_config(page_title="OmniAssistant", page_icon="◉", layout="wide", initial_sidebar_state="expanded")

inicializar_banco()

for chave, padrao in {"historico_mensagens": [], "evidencias_ativas": [], "entrou": False, "splash_visto": False}.items():
    if chave not in st.session_state:
        st.session_state[chave] = padrao

# ---------------------------------------------------------------------------
# TEMA
# Paleta: abismo #06141B | painel #0C2029 | linha #1B3744 | sinal #4FD1C5 | ambar #FFB347
# ---------------------------------------------------------------------------
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Unbounded:wght@300;500;700&family=IBM+Plex+Sans:wght@300;400;500&display=swap');

:root{
  --abismo:#06141B; --painel:#0C2029; --linha:#1B3744;
  --texto:#E6F1F2; --suave:#7F9AA3; --sinal:#4FD1C5; --ambar:#FFB347;
}
html, body, .stApp, [data-testid="stMarkdownContainer"], input, textarea, button{
  font-family:'IBM Plex Sans',sans-serif !important;
}
.stApp{
  background:
    radial-gradient(900px 500px at 85% -10%, rgba(79,209,197,.10), transparent 60%),
    radial-gradient(700px 400px at -10% 110%, rgba(255,179,71,.06), transparent 60%),
    var(--abismo);
  color:var(--texto);
}
#MainMenu, footer{visibility:hidden;}
header[data-testid="stHeader"]{background:transparent;}
.block-container{padding-top:2.2rem; max-width:1200px;}

h1,h2,h3{font-family:'Unbounded',sans-serif !important; letter-spacing:-.01em; font-weight:500 !important;}
h1{font-size:1.9rem !important;}
h2,h3{font-size:1.05rem !important; color:var(--texto);}

/* Barra lateral */
[data-testid="stSidebar"]{background:var(--painel); border-right:1px solid var(--linha);}
[data-testid="stSidebar"] h2{font-size:.95rem !important;}
[data-testid="stFileUploaderDropzone"]{
  background:rgba(79,209,197,.04); border:1px dashed var(--linha); border-radius:14px;
  transition:border-color .2s, background .2s;
}
[data-testid="stFileUploaderDropzone"]:hover{border-color:var(--sinal); background:rgba(79,209,197,.09);}

/* Botoes */
.stButton>button{
  background:transparent; color:var(--texto); border:1px solid var(--linha);
  border-radius:999px; padding:.55rem 1.4rem; transition:all .2s;
}
.stButton>button:hover{border-color:var(--sinal); color:var(--sinal); background:rgba(79,209,197,.07);}
.stButton>button:focus-visible{outline:2px solid var(--ambar); outline-offset:2px;}
.stButton>button[kind="primary"]{
  background:var(--ambar); color:#1A1204; border-color:var(--ambar); font-weight:500;
}
.stButton>button[kind="primary"]:hover{background:#FFC46B; color:#1A1204; border-color:#FFC46B;}

/* Chat */
[data-testid="stChatMessage"]{
  background:var(--painel); border:1px solid var(--linha); border-radius:16px; padding:1rem 1.2rem;
}
[data-testid="stChatInput"]{border-radius:16px; border:1px solid var(--linha); background:var(--painel);}
[data-testid="stChatInput"]:focus-within{border-color:var(--sinal);}

/* Expanders e imagens */
[data-testid="stExpander"]{background:var(--painel); border:1px solid var(--linha); border-radius:12px;}
[data-testid="stImage"] img{border-radius:14px; border:1px solid var(--linha);}

/* Chips de telemetria */
.chips{display:flex; gap:.5rem; flex-wrap:wrap; margin-top:.6rem;}
.chip{font-size:.78rem; color:var(--suave); border:1px solid var(--linha); border-radius:999px; padding:.2rem .7rem;}
.chip b{color:var(--sinal); font-weight:500;}

/* Marca no topo */
.marca{display:flex; align-items:baseline; gap:.9rem; margin-bottom:.2rem;}
.marca .pt{width:10px; height:10px; border-radius:50%; background:var(--ambar); box-shadow:0 0 14px var(--ambar);}
.sub{color:var(--suave); margin:0 0 1.4rem 0; max-width:62ch;}

/* ---------------- SPLASH ---------------- */
.splash{
  position:fixed; inset:0; z-index:999999; background:var(--abismo);
  display:flex; flex-direction:column; align-items:center; justify-content:center; gap:2.2rem;
  animation:splash-sai .8s ease 5.7s forwards;
}
.rings{position:relative; width:200px; height:200px;}
.rings span{
  position:absolute; inset:0; border-radius:50%; border:1px solid var(--sinal); opacity:0;
  animation:onda 2.4s ease-out infinite;
}
.rings span:nth-child(2){animation-delay:.8s;}
.rings span:nth-child(3){animation-delay:1.6s;}
.rings i{
  position:absolute; left:50%; top:50%; width:14px; height:14px; margin:-7px 0 0 -7px;
  border-radius:50%; background:var(--ambar); box-shadow:0 0 28px 6px rgba(255,179,71,.55);
}
.splash-nome{font-family:'Unbounded',sans-serif; font-size:1.5rem; font-weight:300; letter-spacing:.04em;}
.splash-nome b{font-weight:700;}
.barra{width:240px; height:2px; background:var(--linha); overflow:hidden; border-radius:2px;}
.barra i{display:block; height:100%; width:0; background:var(--sinal); animation:carrega 5.5s cubic-bezier(.5,0,.2,1) forwards;}
.status{position:relative; height:1.2rem; width:300px; text-align:center; color:var(--suave); font-size:.85rem;}
.status span{position:absolute; left:0; right:0; opacity:0; animation:msg 1.9s ease forwards;}
.status span:nth-child(2){animation-delay:1.8s;}
.status span:nth-child(3){animation-delay:3.6s;}
@keyframes onda{0%{transform:scale(.15); opacity:.9;} 100%{transform:scale(1); opacity:0;}}
@keyframes carrega{to{width:100%;}}
@keyframes msg{0%{opacity:0; transform:translateY(5px);} 15%,85%{opacity:1; transform:none;} 100%{opacity:0;}}
@keyframes splash-sai{to{opacity:0; visibility:hidden;}}
@media (prefers-reduced-motion: reduce){
  .rings span,.barra i,.status span{animation:none;}
  .status span:first-child{opacity:1;}
  .splash{animation:splash-sai .3s ease 1s forwards;}
}

/* ---------------- CAPA ---------------- */
.capa{padding:9vh 0 4vh 0;}
.capa h1{font-size:clamp(2.6rem,7vw,5.2rem) !important; line-height:1.02; font-weight:700 !important; margin:0 0 1.4rem 0;}
.capa h1 em{font-style:normal; font-weight:300; color:var(--sinal);}
.capa p.lead{font-size:1.15rem; color:var(--suave); max-width:52ch; line-height:1.6; margin:0 0 3rem 0;}
.trio{display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:2rem; margin-bottom:3rem;}
.trio div{border-top:1px solid var(--linha); padding-top:1rem;}
.trio h3{margin:0 0 .4rem 0 !important; color:var(--ambar) !important;}
.trio p{margin:0; color:var(--suave); font-size:.95rem; line-height:1.55;}
@media (max-width:720px){.trio{grid-template-columns:1fr;}}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# Splash: aparece uma unica vez por sessao e some sozinho (CSS puro)
if not st.session_state["splash_visto"]:
    st.markdown(
        """<div class="splash">
<div class="rings"><span></span><span></span><span></span><i></i></div>
<div class="splash-nome">Omni<b>Assistant</b></div>
<div class="barra"><i></i></div>
<div class="status"><span>Carregando modelo de visão</span><span>Preparando transcrição de áudio</span><span>Conectando ao banco local</span></div>
</div>""",
        unsafe_allow_html=True,
    )
    st.session_state["splash_visto"] = True

# ---------------------------------------------------------------------------
# CAPA
# ---------------------------------------------------------------------------
if not st.session_state["entrou"]:
    st.markdown(
        """<style>[data-testid="stSidebar"], [data-testid="collapsedControl"], [data-testid="stSidebarCollapsedControl"]{display:none;}</style>
<div class="capa">
<h1>Veja, ouça<br><em>e pergunte.</em></h1>
<p class="lead">Envie um print, um diagrama ou um áudio de comando. O OmniAssistant cruza tudo com os dados da empresa e mostra cada passo do raciocínio.</p>
<div class="trio">
<div><h3>Imagens</h3><p>Prints e diagramas são lidos e viram contexto para a conversa.</p></div>
<div><h3>Áudios</h3><p>Comandos falados são transcritos com Whisper e entendidos como pedidos.</p></div>
<div><h3>Consultas</h3><p>O agente consulta o banco local e registra as ferramentas que usou.</p></div>
</div>
</div>""",
        unsafe_allow_html=True,
    )
    if st.button("Abrir o assistente", type="primary"):
        st.session_state["entrou"] = True
        st.rerun()
    st.stop()

# ---------------------------------------------------------------------------
# APLICACAO
# ---------------------------------------------------------------------------
st.markdown('<div class="marca"><span class="pt"></span></div>', unsafe_allow_html=True)
st.title("OmniAssistant")
st.markdown(
    '<p class="sub">Análise integrada de imagens, áudios de comando e consultas corporativas.</p>',
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("Entradas")
    upload_img = st.file_uploader("Imagem (print ou diagrama)", type=["png", "jpg", "jpeg"])
    upload_audio = st.file_uploader("Áudio de comando", type=["wav", "mp3", "ogg"])

    if st.button("Limpar sessão e cache"):
        st.session_state["historico_mensagens"].clear()
        st.session_state["evidencias_ativas"].clear()
        st.rerun()
    if st.button("Voltar à capa"):
        st.session_state["entrou"] = False
        st.rerun()

novas_evidencias = []
col_preview1, col_preview2 = st.columns(2)

if upload_img:
    with col_preview1:
        st.subheader("Imagem")
        st.image(upload_img, use_container_width=True)
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
        st.subheader("Áudio")
        st.audio(upload_audio)
        with TemporaryDirectory() as tmp_dir:
            caminho_tmp = Path(tmp_dir) / upload_audio.name
            caminho_tmp.write_bytes(upload_audio.getvalue())
            try:
                ev_audio = despachar_ingestao(EntradaUsuario(tipo="audio", caminho_arquivo=caminho_tmp))
                novas_evidencias.append(ev_audio)
                with st.expander("Transcrição Whisper"):
                    st.write(ev_audio.resumo_informacao)
            except Exception as e:
                st.error(f"Erro ao processar áudio: {e}")

st.session_state["evidencias_ativas"] = novas_evidencias

# Historico com painel de telemetria
for msg in st.session_state["historico_mensagens"]:
    with st.chat_message(msg["papel"]):
        st.write(msg["conteudo"])

        telemetria = msg.get("telemetria")
        if telemetria:
            tempo_ms = telemetria.get("tempo_total_ms", 0)
            tokens = telemetria.get("tokens_estimados", "N/A")
            turnos = telemetria.get("total_turnos", 1)

            st.markdown(
                f'<div class="chips"><span class="chip">Tempo <b>{tempo_ms} ms</b></span>'
                f'<span class="chip">Turnos <b>{turnos}</b></span>'
                f'<span class="chip">Tokens <b>{tokens}</b></span></div>',
                unsafe_allow_html=True,
            )

            rastro = telemetria.get("rastro_ferramentas", [])
            if rastro:
                with st.expander(f"Auditoria de ferramentas ({len(rastro)} ações)"):
                    for idx, tool in enumerate(rastro, start=1):
                        st.markdown(f"**{idx}. Ferramenta:** `{tool['ferramenta']}` ({tool.get('duracao_ms', 0)} ms)")
                        st.json({"argumentos": tool["argumentos"], "resultado_banco": tool["resultado"]})

comando_chat = st.chat_input("Pergunte sobre as evidências ou peça uma ação")
if comando_chat:
    st.session_state["historico_mensagens"].append({"papel": "user", "conteudo": comando_chat})

    with st.spinner("Raciocinando e consultando ferramentas..."):
        try:
            resultado = executar_agente(comando_chat, st.session_state["evidencias_ativas"])
            st.session_state["historico_mensagens"].append({
                "papel": "assistant",
                "conteudo": resultado["resposta"],
                "telemetria": resultado,
            })
        except Exception as e:
            st.session_state["historico_mensagens"].append({
                "papel": "assistant",
                "conteudo": f"Falha na execução: {type(e).__name__} - {e}",
            })
    st.rerun()