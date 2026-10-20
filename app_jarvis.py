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
# TEMA HUD
# Paleta: vazio #02080F | ciano #00E0FF | texto #BFEFFA | reator #FF7A1A
# ---------------------------------------------------------------------------
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;500;700;900&family=Rajdhani:wght@400;500;600&family=Share+Tech+Mono&display=swap');

@property --n{syntax:'<integer>'; inherits:false; initial-value:0;}

:root{
  --vazio:#02080F; --painel:rgba(4,24,38,.72); --linha:rgba(0,224,255,.30);
  --ciano:#00E0FF; --texto:#BFEFFA; --suave:#6FA3B3; --reator:#FF7A1A;
  --chanfro:polygon(14px 0,100% 0,100% calc(100% - 14px),calc(100% - 14px) 100%,0 100%,0 14px);
}
html, body, .stApp, [data-testid="stMarkdownContainer"], input, textarea, button{
  font-family:'Rajdhani',sans-serif !important; font-size:1.05rem;
}
.stApp{
  color:var(--texto);
  background:
    radial-gradient(900px 520px at 78% -8%, rgba(0,224,255,.14), transparent 60%),
    radial-gradient(600px 360px at 0% 105%, rgba(255,122,26,.07), transparent 60%),
    linear-gradient(rgba(0,224,255,.045) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0,224,255,.045) 1px, transparent 1px),
    var(--vazio);
  background-size:auto, auto, 44px 44px, 44px 44px, auto;
}
#MainMenu, footer{visibility:hidden;}
header[data-testid="stHeader"]{background:transparent;}
.block-container{padding-top:2rem; max-width:1200px;}

h1,h2,h3{font-family:'Orbitron',sans-serif !important; font-weight:500 !important; letter-spacing:.08em; text-transform:uppercase;}
h1{font-size:1.7rem !important; color:var(--ciano); text-shadow:0 0 18px rgba(0,224,255,.45);}
h2,h3{font-size:.95rem !important; color:var(--texto);}

/* Barra lateral */
[data-testid="stSidebar"]{background:rgba(2,12,20,.92); border-right:1px solid var(--linha);}
[data-testid="stFileUploaderDropzone"]{
  background:rgba(0,224,255,.04); border:1px dashed var(--linha); border-radius:0;
  clip-path:var(--chanfro); transition:background .2s, border-color .2s;
}
[data-testid="stFileUploaderDropzone"]:hover{background:rgba(0,224,255,.10); border-color:var(--ciano);}

/* Botoes */
.stButton>button{
  background:rgba(0,224,255,.05); color:var(--texto); border:1px solid var(--linha); border-radius:0;
  clip-path:var(--chanfro); padding:.6rem 1.6rem; letter-spacing:.14em; text-transform:uppercase;
  font-weight:600; transition:all .2s;
}
.stButton>button:hover{border-color:var(--ciano); color:var(--ciano); background:rgba(0,224,255,.14); box-shadow:0 0 18px rgba(0,224,255,.35);}
.stButton>button:focus-visible{outline:2px solid var(--reator); outline-offset:2px;}
.stButton>button[kind="primary"]{
  background:rgba(255,122,26,.12); color:var(--reator); border-color:var(--reator);
}
.stButton>button[kind="primary"]:hover{background:rgba(255,122,26,.25); color:#FFB27A; border-color:#FFB27A; box-shadow:0 0 22px rgba(255,122,26,.45);}

/* Chat */
[data-testid="stChatMessage"]{
  background:var(--painel); border:1px solid var(--linha); border-radius:0; clip-path:var(--chanfro);
  padding:1rem 1.3rem; backdrop-filter:blur(6px);
}
[data-testid="stChatInput"]{border-radius:0; border:1px solid var(--linha); background:var(--painel);}
[data-testid="stChatInput"]:focus-within{border-color:var(--ciano); box-shadow:0 0 16px rgba(0,224,255,.3);}

/* Expanders e imagens */
[data-testid="stExpander"]{background:var(--painel); border:1px solid var(--linha); border-radius:0; clip-path:var(--chanfro);}
[data-testid="stImage"] img{border:1px solid var(--linha); border-radius:0;}

/* Leituras de telemetria */
.chips{display:flex; gap:.6rem; flex-wrap:wrap; margin-top:.7rem; font-family:'Share Tech Mono',monospace;}
.chip{font-family:'Share Tech Mono',monospace !important; font-size:.8rem; color:var(--suave); border:1px solid var(--linha); padding:.15rem .7rem;}
.chip b{color:var(--ciano); font-weight:400;}

/* Status no topo */
.online{display:flex; align-items:center; gap:.6rem; font-family:'Share Tech Mono',monospace; font-size:.8rem; color:var(--suave); margin-bottom:.4rem;}
.online i{width:8px; height:8px; border-radius:50%; background:var(--ciano); box-shadow:0 0 10px var(--ciano); animation:pisca 1.6s ease-in-out infinite;}
.sub{color:var(--suave); margin:0 0 1.4rem 0; max-width:62ch;}
@keyframes pisca{50%{opacity:.25;}}

/* ---------------- ANEIS (loading e capa) ---------------- */
.hud{position:relative; width:var(--d,260px); height:var(--d,260px); flex:none;}
.hud b{position:absolute; border-radius:50%; display:block;}
.hud .a1{inset:0; border:1px solid rgba(0,224,255,.35);}
.hud .a2{inset:8%; border:3px dashed rgba(0,224,255,.55); animation:gira 18s linear infinite;}
.hud .a3{
  inset:19%; background:repeating-conic-gradient(var(--ciano) 0 1.2deg, transparent 1.2deg 7.5deg);
  -webkit-mask:radial-gradient(circle, transparent 82%, #000 83%, #000 100%);
          mask:radial-gradient(circle, transparent 82%, #000 83%, #000 100%);
  animation:gira 26s linear infinite reverse;
}
.hud .a4{inset:30%; border:2px solid transparent; border-top-color:var(--ciano); border-bottom-color:var(--ciano); animation:gira 4s linear infinite;}
.hud .a5{inset:40%; border:1px dotted rgba(0,224,255,.8); animation:gira 9s linear infinite reverse;}
.hud .nucleo{
  inset:44%; background:radial-gradient(circle, #fff 0 12%, var(--ciano) 40%, rgba(0,224,255,0) 72%);
  box-shadow:0 0 40px 8px rgba(0,224,255,.55); animation:bate 2.4s ease-in-out infinite;
}
@keyframes gira{to{transform:rotate(360deg);}}
@keyframes bate{50%{transform:scale(1.25); box-shadow:0 0 60px 14px rgba(0,224,255,.7);}}

/* ---------------- SPLASH ---------------- */
.splash{
  position:fixed; inset:0; z-index:999999; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:1.8rem;
  background:
    radial-gradient(700px 420px at 50% 40%, rgba(0,224,255,.12), transparent 65%),
    linear-gradient(rgba(0,224,255,.045) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0,224,255,.045) 1px, transparent 1px),
    var(--vazio);
  background-size:auto, 44px 44px, 44px 44px, auto;
  animation:splash-sai .8s ease 5.7s forwards;
}
.splash .hud{--d:280px;}
.splash-nome{font-family:'Orbitron',sans-serif; font-weight:900; font-size:1.7rem; letter-spacing:.35em; color:var(--ciano); text-shadow:0 0 22px rgba(0,224,255,.6); padding-left:.35em;}
.carga{display:flex; align-items:center; gap:1rem; width:340px;}
.barra{flex:1; height:3px; background:rgba(0,224,255,.18); overflow:hidden;}
.barra i{display:block; height:100%; width:0; background:var(--ciano); box-shadow:0 0 12px var(--ciano); animation:carrega 5.5s cubic-bezier(.5,0,.2,1) forwards;}
.pct{font-family:'Share Tech Mono',monospace; font-size:.9rem; color:var(--ciano); width:3.2rem; text-align:right; animation:conta 5.5s cubic-bezier(.5,0,.2,1) forwards;}
.pct::after{counter-reset:n var(--n); content:counter(n) "%";}
.log{width:340px; min-height:6.6rem; font-family:'Share Tech Mono',monospace; font-size:.85rem; color:var(--suave); display:flex; flex-direction:column; gap:.25rem;}
.log span{opacity:0; animation:linha .3s ease forwards;}
.log span em{font-style:normal; color:var(--ciano); float:right;}
.log span:nth-child(1){animation-delay:.4s;}
.log span:nth-child(2){animation-delay:1.5s;}
.log span:nth-child(3){animation-delay:2.6s;}
.log span:nth-child(4){animation-delay:3.7s;}
.log span:nth-child(5){animation-delay:4.8s;}
@keyframes carrega{to{width:100%;}}
@keyframes conta{to{--n:100;}}
@keyframes linha{to{opacity:1;}}
@keyframes splash-sai{to{opacity:0; visibility:hidden;}}
@media (prefers-reduced-motion: reduce){
  .hud b,.online i,.barra i,.pct{animation:none;}
  .barra i{width:100%;}
  .pct::after{content:"100%"; counter-reset:none;}
  .log span{opacity:1; animation:none;}
  .splash{animation:splash-sai .3s ease 1.2s forwards;}
}

/* ---------------- CAPA ---------------- */
.capa{display:grid; grid-template-columns:minmax(0,1.25fr) minmax(0,1fr); gap:3rem; align-items:center; padding:7vh 0 3vh 0;}
.capa h1{font-size:clamp(2.2rem,5.4vw,4.2rem) !important; line-height:1.08; font-weight:900 !important; margin:0 0 1.4rem 0; letter-spacing:.06em;}
.capa .lead{font-size:1.25rem; color:var(--suave); max-width:48ch; line-height:1.5; margin:0 0 2.2rem 0;}
.capa .grafico{display:flex; justify-content:center;}
.capa .hud{--d:min(380px,38vw);}
.modulos{display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:1.4rem; margin-bottom:2rem;}
.modulos div{border-left:2px solid var(--ciano); padding-left:.9rem;}
.modulos h3{margin:0 0 .3rem 0 !important; color:var(--ciano) !important;}
.modulos p{margin:0; color:var(--suave); font-size:.98rem; line-height:1.4;}
@media (max-width:860px){.capa{grid-template-columns:1fr;} .capa .grafico{order:-1;} .modulos{grid-template-columns:1fr;}}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# Splash: uma unica vez por sessao, some sozinho (CSS puro)
if not st.session_state["splash_visto"]:
    st.markdown(
        """<div class="splash">
<div class="hud"><b class="a1"></b><b class="a2"></b><b class="a3"></b><b class="a4"></b><b class="a5"></b><b class="nucleo"></b></div>
<div class="splash-nome">OMNIASSISTANT</div>
<div class="carga"><div class="barra"><i></i></div><div class="pct"></div></div>
<div class="log">
<span>módulo de visão <em>OK</em></span>
<span>transcrição de áudio <em>OK</em></span>
<span>banco de dados local <em>OK</em></span>
<span>núcleo do agente <em>OK</em></span>
<span>sistemas online <em>OK</em></span>
</div>
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
<div>
<div class="online"><i></i>sistema online</div>
<h1>Omni<br>Assistant</h1>
<p class="lead">Envie um print, um diagrama ou um áudio de comando. O assistente cruza tudo com os dados da empresa e mostra cada passo do raciocínio.</p>
<div class="modulos">
<div><h3>Visão</h3><p>Prints e diagramas viram contexto para a conversa.</p></div>
<div><h3>Voz</h3><p>Comandos falados são transcritos com Whisper.</p></div>
<div><h3>Dados</h3><p>Consultas ao banco local com auditoria de cada ferramenta.</p></div>
</div>
</div>
<div class="grafico"><div class="hud"><b class="a1"></b><b class="a2"></b><b class="a3"></b><b class="a4"></b><b class="a5"></b><b class="nucleo"></b></div></div>
</div>""",
        unsafe_allow_html=True,
    )
    if st.button("Iniciar sistema", type="primary"):
        st.session_state["entrou"] = True
        st.rerun()
    st.stop()

# ---------------------------------------------------------------------------
# APLICACAO
# ---------------------------------------------------------------------------
st.markdown('<div class="online"><i></i>sistema online</div>', unsafe_allow_html=True)
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

for msg in st.session_state["historico_mensagens"]:
    with st.chat_message(msg["papel"]):
        st.write(msg["conteudo"])

        telemetria = msg.get("telemetria")
        if telemetria:
            tempo_ms = telemetria.get("tempo_total_ms", 0)
            tokens = telemetria.get("tokens_estimados", "N/A")
            turnos = telemetria.get("total_turnos", 1)

            st.markdown(
                f'<div class="chips"><span class="chip">TEMPO <b>{tempo_ms} ms</b></span>'
                f'<span class="chip">TURNOS <b>{turnos}</b></span>'
                f'<span class="chip">TOKENS <b>{tokens}</b></span></div>',
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