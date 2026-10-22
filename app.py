import hashlib
import html
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import sleep
from tempfile import TemporaryDirectory
import streamlit as st
from dotenv import load_dotenv
from src.core.contracts import EntradaUsuario, EvidenciaMultimodal
from src.core.ingestion import despachar_ingestao
from src.core.agent import executar_agente
from src.core.contracts import RegistroConversa
from src.core.exportacao import montar_csv_financeiro
from src.core.finalizacao import finalizar_registro
from src.core.voz import ESTILOS, RITMOS, TAMANHOS, TAMANHO_PADRAO, VOZES, preparar_voz
from src.tools.local import inicializar_banco
from src.tools.dados import inicializar_dados

st.set_page_config(page_title="NAVI", page_icon="◉", layout="wide", initial_sidebar_state="expanded")

inicializar_banco()


@st.cache_resource
def preparar_dados():
    """Cria as tabelas de clientes e notas e carrega os exemplos (uma vez por processo)."""
    inicializar_dados()


preparar_dados()

for chave, padrao in {
    "historico_mensagens": [],
    "evidencias_ativas": [],
    "entrou": False,
    "splash_visto": False,
    "mic_processado": None,
    "pergunta_pendente": None,
}.items():
    if chave not in st.session_state:
        st.session_state[chave] = padrao


@st.cache_data(show_spinner="Processando evidência...", max_entries=32)
def ingerir_cache(tipo: str, nome: str, conteudo: bytes):
    """Ingere imagem/áudio uma única vez por arquivo (cache pelo conteúdo)."""
    with TemporaryDirectory() as tmp_dir:
        caminho_tmp = Path(tmp_dir) / nome
        caminho_tmp.write_bytes(conteudo)
        return despachar_ingestao(
            EntradaUsuario(tipo=tipo, caminho_arquivo=caminho_tmp)
        )


def digitar(texto: str):
    """Efeito de digitação para a resposta (limitado a ~3 s no total)."""
    palavras = texto.split(" ")
    atraso = min(0.02, 3.0 / max(len(palavras), 1))
    for palavra in palavras:
        yield palavra + " "
        sleep(atraso)


def renderizar_voz(voz: dict, autoplay: bool = False):
    """Só o player fica visível; o texto do resumo fica recolhido."""
    st.markdown('<div class="voz"><b>RESPOSTA FALADA</b></div>', unsafe_allow_html=True)
    try:
        st.audio(voz["audio"], format="audio/wav", autoplay=autoplay)
    except TypeError:  # versões antigas do Streamlit não têm autoplay
        st.audio(voz["audio"], format="audio/wav")
    with st.expander("Ver texto do resumo falado"):
        st.write(voz["resumo"])


def montar_markdown(
    pergunta: str, resposta: str, telemetria: dict | None = None
) -> str:
    """Monta o .md da resposta: pergunta, resposta, risco e ferramentas usadas."""
    partes = []
    if pergunta:
        partes.append(f"## Pergunta\n\n{pergunta}\n")
    partes.append(f"## Resposta\n\n{resposta}\n")

    if telemetria:
        risco = telemetria.get("risco")
        if risco and risco.get("nivel") != "neutro":
            motivos = "; ".join(risco.get("motivos", []))
            partes.append(
                f"## Risco\n\n**{risco['rotulo']}**"
                + (f" — {motivos}" if motivos else "")
                + "\n"
            )

        rastro = telemetria.get("rastro_ferramentas", [])
        if rastro:
            linhas = ["## Ferramentas utilizadas\n"]
            for i, tool in enumerate(rastro, start=1):
                linhas.append(
                    f"{i}. `{tool['ferramenta']}` ({tool.get('duracao_ms', 0)} ms)"
                )
                sql = tool.get("argumentos", {}).get("sql")
                if sql:
                    linhas.append(f"\n```sql\n{sql.strip()}\n```\n")
            partes.append("\n".join(linhas))

        partes.append(
            f"---\n*Tempo: {telemetria.get('tempo_total_ms', 0)} ms · "
            f"Turnos: {telemetria.get('total_turnos', 1)} · "
            f"Tokens: {telemetria.get('tokens_estimados', 'N/A')}*"
        )
    return "\n".join(partes)


def renderizar_exportacao(
    pergunta: str, resposta: str, telemetria: dict | None, chave: str
):
    st.download_button(
        "Exportar .md",
        data=montar_markdown(pergunta, resposta, telemetria).encode("utf-8"),
        file_name="resposta_omniassistant.md",
        mime="text/markdown",
        key=chave,
    )


def renderizar_exportacao_financeira(historico: list[dict]):
    conteudo = montar_csv_financeiro(historico)
    if not conteudo:
        return
    st.download_button(
        "Exportar dados bancários (.csv)",
        data=conteudo.encode("utf-8"),
        file_name="dados_bancarios_omniassistant.csv",
        mime="text/csv",
        key="csv_financeiro",
        help="Baixa somente as notas e clientes citados nas análises desta conversa.",
    )


def renderizar_finalizacao(registro_dict: dict, chave: str):
    """Exibe revisão explícita e só executa integrações após confirmação."""
    registro = RegistroConversa.model_validate(registro_dict)
    with st.expander("Enviar dados da análise", expanded=False):
        st.caption("Revise os dados. Nenhuma integração é executada sem confirmação.")
        with st.form(f"form_finalizacao_{chave}"):
            email = st.text_input(
                "E-mail do destinatário", value=registro.destinatario_email or ""
            )
            cliente = st.text_input("Cliente", value=registro.cliente or "")
            nota = st.text_input("Número da nota", value=registro.numero_nota or "")
            total = st.number_input(
                "Total (BRL)",
                min_value=0.0,
                value=float(registro.total or 0.0),
                step=0.01,
            )
            confirmar = st.checkbox(
                "Confirmo que os dados foram revisados", key=f"confirmar_{chave}"
            )
            executar = st.form_submit_button("Enviar e-mail", type="primary")

        if executar:
            if not confirmar:
                st.error("Confirme a revisão dos dados antes de executar.")
                return
            atualizado = registro.model_copy(
                update={
                    "destinatario_email": email.strip() or None,
                    "cliente": cliente.strip() or None,
                    "numero_nota": nota.strip() or None,
                    "total": total or None,
                }
            )
            try:
                resultado = finalizar_registro(
                    atualizado,
                )
                st.success(
                    f"Operação concluída: {json.dumps(resultado, ensure_ascii=False)}"
                )
            except Exception as exc:
                st.error(f"Operação não concluída: {type(exc).__name__} - {exc}")


def renderizar_risco(risco: dict):
    if not risco or risco.get("nivel") == "neutro":
        return
    motivos = " · ".join(html.escape(m) for m in risco.get("motivos", []))
    st.markdown(
        f'<div class="risco {risco["nivel"]}"><i></i><b>{html.escape(risco["rotulo"])}</b><span>{motivos}</span></div>',
        unsafe_allow_html=True,
    )


def renderizar_telemetria(telemetria: dict):
    """Semáforo de risco sempre visível; chips e auditoria ficam num único expander."""
    renderizar_risco(telemetria.get("risco"))
    tempo_ms = telemetria.get("tempo_total_ms", 0)
    tokens = telemetria.get("tokens_estimados", "N/A")
    turnos = telemetria.get("total_turnos", 1)
    rastro = telemetria.get("rastro_ferramentas", [])

    titulo = f"Detalhes · {tempo_ms} ms · {len(rastro)} ferramenta(s)"
    with st.expander(titulo):
        st.markdown(
            f'<div class="chips"><span class="chip">TEMPO <b>{tempo_ms} ms</b></span>'
            f'<span class="chip">TURNOS <b>{turnos}</b></span>'
            f'<span class="chip">TOKENS <b>{tokens}</b></span></div>',
            unsafe_allow_html=True,
        )
        # Sem expander interno: o Streamlit não aceita expander dentro de expander.
        for idx, tool in enumerate(rastro, start=1):
            st.markdown(
                f"**{idx}. Ferramenta:** `{tool['ferramenta']}` ({tool.get('duracao_ms', 0)} ms)"
            )
            res = tool["resultado"] or {}
            if tool["ferramenta"] == "consultar_banco" and res.get("colunas"):
                st.code(tool["argumentos"].get("sql", ""), language="sql")
                st.dataframe(
                    [dict(zip(res["colunas"], linha)) for linha in res["linhas"]],
                    use_container_width=True,
                )
                if res.get("truncado"):
                    st.caption("Resultado truncado no limite de linhas.")
            else:
                st.json(
                    {
                        "argumentos": tool["argumentos"],
                        "resultado_banco": tool["resultado"],
                    }
                )


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

/* Botoes (inclui o botao de exportar) */
.stButton>button, .stDownloadButton>button{
  background:rgba(0,224,255,.05); color:var(--texto); border:1px solid var(--linha); border-radius:0;
  clip-path:var(--chanfro); padding:.6rem 1.6rem; letter-spacing:.14em; text-transform:uppercase;
  font-weight:600; transition:all .2s;
}
.stButton>button:hover, .stDownloadButton>button:hover{
  border-color:var(--ciano); color:var(--ciano); background:rgba(0,224,255,.14); box-shadow:0 0 18px rgba(0,224,255,.35);
}
.stButton>button:focus-visible, .stDownloadButton>button:focus-visible{outline:2px solid var(--reator); outline-offset:2px;}
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

/* Avatares do chat: nucleo (assistente) e silhueta (usuario) */
[data-testid="stChatMessageAvatarUser"],
[data-testid="stChatMessageAvatarAssistant"],
[data-testid="chatAvatarIcon-user"],
[data-testid="chatAvatarIcon-assistant"]{
  width:2.2rem !important; height:2.2rem !important; border-radius:0 !important;
  background-color:#041826 !important; border:1px solid var(--ciano);
  clip-path:polygon(7px 0,100% 0,100% calc(100% - 7px),calc(100% - 7px) 100%,0 100%,0 7px);
}
[data-testid="stChatMessageAvatarUser"] > *,
[data-testid="stChatMessageAvatarAssistant"] > *,
[data-testid="chatAvatarIcon-user"] > *,
[data-testid="chatAvatarIcon-assistant"] > *{opacity:0 !important;}
[data-testid="stChatMessageAvatarAssistant"],
[data-testid="chatAvatarIcon-assistant"]{
  background-image:radial-gradient(circle, #fff 0 9%, var(--ciano) 24%, rgba(0,224,255,0) 60%) !important;
  box-shadow:inset 0 0 12px rgba(0,224,255,.55);
}
[data-testid="stChatMessageAvatarUser"],
[data-testid="chatAvatarIcon-user"]{
  border-color:var(--reator);
  background-image:radial-gradient(circle, #fff 0 9%, var(--reator) 24%, rgba(255,122,26,0) 60%) !important;
  box-shadow:inset 0 0 12px rgba(255,122,26,.55);
}

/* Expanders e imagens */
[data-testid="stExpander"]{background:var(--painel); border:1px solid var(--linha); border-radius:0; clip-path:var(--chanfro);}
[data-testid="stImage"] img{border:1px solid var(--linha); border-radius:0;}

/* Leituras de telemetria */
.chips{display:flex; gap:.6rem; flex-wrap:wrap; margin-top:.7rem; font-family:'Share Tech Mono',monospace;}
.chip{font-family:'Share Tech Mono',monospace !important; font-size:.8rem; color:var(--suave); border:1px solid var(--linha); padding:.15rem .7rem;}
.chip b{color:var(--ciano); font-weight:400;}

.voz{margin-top:.8rem; padding:.55rem .9rem; border-left:2px solid var(--reator); background:rgba(255,122,26,.06); color:var(--texto);}
.voz b{font-family:'Share Tech Mono',monospace; font-weight:400; font-size:.75rem; letter-spacing:.14em; color:var(--reator); margin-right:.6rem;}

.risco{--cor:var(--suave); display:flex; align-items:flex-start; gap:.7rem; margin-top:.9rem; padding:.55rem .9rem;
  border:1px solid var(--cor); border-left-width:4px; background:rgba(255,255,255,.02);}
.risco i{flex:none; width:10px; height:10px; margin-top:.45rem; border-radius:50%; background:var(--cor); box-shadow:0 0 12px var(--cor);}
.risco b{flex:none; font-family:'Orbitron',sans-serif; font-weight:500; font-size:.78rem; letter-spacing:.14em; color:var(--cor); margin-top:.1rem;}
.risco span{color:var(--texto); font-size:.98rem;}
.risco.verde{--cor:#3DDC97;}
.risco.amarelo{--cor:#FFC53D;}
.risco.vermelho{--cor:#FF4D4D;}

/* Passos do raciocinio ao vivo */
.passo{font-family:'Share Tech Mono',monospace; font-size:.85rem; color:var(--suave); padding:.1rem 0;}
.passo span{color:var(--ciano);}
.passo code{color:var(--texto); background:rgba(0,224,255,.08); padding:0 .35rem;}
.passo em{font-style:normal; color:var(--ciano); float:right;}
.passo em.erro{color:var(--reator);}

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
.capa{display:grid; grid-template-columns:minmax(0,1fr) auto minmax(0,1fr); gap:3rem; align-items:center; padding:6vh 0 2vh 0;}
.capa .centro{display:flex; flex-direction:column; align-items:center; text-align:center; gap:1.2rem; max-width:36ch;}
.capa .centro .hud{--d:min(340px,28vw);}
.capa h1{font-size:clamp(2.2rem,5vw,3.6rem) !important; font-weight:900 !important; margin:0; letter-spacing:.35em; padding-left:.35em;}
.capa .lead{font-size:1.1rem; color:var(--suave); line-height:1.5; margin:0;}
.capa .lado{display:flex; flex-direction:column; gap:2.2rem;}
.capa .lado div{border-left:2px solid var(--ciano); padding-left:.9rem;}
.capa .lado.dir{text-align:right;}
.capa .lado.dir div{border-left:0; border-right:2px solid var(--ciano); padding:0 .9rem 0 0;}
.capa .lado h3{margin:0 0 .3rem 0 !important; color:var(--ciano) !important;}
.capa .lado p{margin:0; color:var(--suave); font-size:.98rem; line-height:1.4;}
@media (max-width:860px){
  .capa{grid-template-columns:1fr; gap:2rem;}
  .capa .centro{order:-1; max-width:none;}
  .capa .centro .hud{--d:220px;}
  .capa .lado.dir{text-align:left;}
  .capa .lado.dir div{border-right:0; border-left:2px solid var(--ciano); padding:0 0 0 .9rem;}
}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# Splash: uma unica vez por sessao, some sozinho (CSS puro)
if not st.session_state["splash_visto"]:
    st.markdown(
        """<div class="splash">
<div class="hud"><b class="a1"></b><b class="a2"></b><b class="a3"></b><b class="a4"></b><b class="a5"></b><b class="nucleo"></b></div>
<div class="splash-nome">NAVI</div>
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
<div class="lado">
<div><h3>Visão</h3><p>Prints e diagramas viram contexto para a conversa.</p></div>
<div><h3>Voz</h3><p>Comandos falados são transcritos com Whisper.</p></div>
</div>
<div class="centro">
<div class="hud"><b class="a1"></b><b class="a2"></b><b class="a3"></b><b class="a4"></b><b class="a5"></b><b class="nucleo"></b></div>
<h1>NAVI</h1>
<p class="lead">Envie um print, um diagrama ou um áudio do seu problema. O assistente que resolve suas dúvidas.</p>
</div>
<div class="lado dir">
<div><h3>Dados</h3><p>Consultas ao banco local com auditoria de cada ferramenta.</p></div>
<div><h3>Raciocínio</h3><p>Cada passo do agente aparece ao vivo na tela.</p></div>
</div>
</div>""",
        unsafe_allow_html=True,
    )
    st.markdown('<div style="height:6vh"></div>', unsafe_allow_html=True)
    _, meio, _ = st.columns([1, 1, 1])
    with meio:
        if st.button("Iniciar sistema", type="primary", use_container_width=True):
            st.session_state["entrou"] = True
            st.rerun()
    st.stop()

# ---------------------------------------------------------------------------
# APLICACAO
# ---------------------------------------------------------------------------
st.markdown('<div class="online"><i></i>sistema online</div>', unsafe_allow_html=True)
st.title("NAVI")
st.markdown(
    '<p class="sub">Análise integrada de imagens, áudios de comando e consultas corporativas.</p>',
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("Entradas")
    upload_imgs = st.file_uploader(
        "Imagens (prints ou diagramas)",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True,
    )
    upload_audios = st.file_uploader(
        "Áudios de comando",
        type=["wav", "mp3", "ogg", "m4a"],
        accept_multiple_files=True,
    )
    mic_audio = st.audio_input("Falar com o assistente") if hasattr(st, "audio_input") else None

    st.header("Voz")
    voz_ativa = st.toggle(
        "Resposta por voz",
        value=False,
        help="Respostas longas são resumidas e o resumo é lido em voz alta. A resposta completa continua na tela.",
    )
    # Valores iniciais: só são usados quando voz_ativa é verdadeiro.
    voz_escolhida, estilo_voz = VOZES[0], list(ESTILOS)[0]
    ritmo_voz, tamanho_resumo = "Ágil", TAMANHO_PADRAO
    if voz_ativa:
        with st.expander("Ajustes da voz"):
            voz_escolhida = st.selectbox("Voz do assistente", VOZES)
            estilo_voz = st.selectbox("Estilo de fala", list(ESTILOS))
            ritmo_voz = st.select_slider(
                "Ritmo da fala", options=list(RITMOS), value="Ágil"
            )
            tamanho_resumo = st.radio(
                "Tamanho do resumo falado",
                list(TAMANHOS),
                index=list(TAMANHOS).index(TAMANHO_PADRAO),
                horizontal=True,
            )

    if st.button("Limpar sessão e cache"):
        st.session_state["historico_mensagens"].clear()
        st.session_state["evidencias_ativas"].clear()
        st.rerun()
    if st.button("Voltar à capa"):
        st.session_state["entrou"] = False
        st.rerun()

novas_evidencias = []
previews_audio = []

if upload_imgs:
    for upload_img in upload_imgs:
        try:
            novas_evidencias.append(ingerir_cache("imagem", upload_img.name, upload_img.getvalue()))
        except Exception as e:
            st.error(f"Erro ao processar imagem '{upload_img.name}': {e}")

fontes_audio = []
for upload_audio in upload_audios or []:
    fontes_audio.append((upload_audio, upload_audio.name, "Áudio", False))
if mic_audio:
    fontes_audio.append((mic_audio, "gravacao.wav", "Gravação", True))

for arquivo, nome, rotulo, eh_mic in fontes_audio:
    try:
        ev_audio = ingerir_cache("audio", nome, arquivo.getvalue())
        novas_evidencias.append(ev_audio)
        previews_audio.append((rotulo, arquivo, ev_audio))

        # Gravação nova no microfone: dispara o comando automaticamente
        if eh_mic:
            marca = hashlib.md5(arquivo.getvalue()).hexdigest()
            if marca != st.session_state["mic_processado"]:
                st.session_state["mic_processado"] = marca
                st.session_state["pergunta_pendente"] = (
                    "Interprete e execute o comando de voz da gravação, "
                    "usando as ferramentas quando necessário."
                )
    except Exception as e:
        st.error(f"Erro ao processar áudio '{nome}': {e}")

# Pré-visualização compacta: tudo dentro de um expander recolhido
if upload_imgs or previews_audio:
    with st.expander(f"Evidências ativas ({len(novas_evidencias)})"):
        if upload_imgs:
            st.markdown("**Imagens**")
            cols = st.columns(min(3, max(1, len(upload_imgs))))
            for idx, upload_img in enumerate(upload_imgs):
                with cols[idx % len(cols)]:
                    st.image(upload_img, width=220, caption=upload_img.name)

        if previews_audio:
            st.markdown("**Áudios**")
            for rotulo, arquivo, ev_audio in previews_audio:
                st.markdown(f"**{rotulo}**")
                st.audio(arquivo)
                st.caption("Transcrição Whisper")
                st.write(ev_audio.resumo_informacao)

st.session_state["evidencias_ativas"] = novas_evidencias

for i, msg in enumerate(st.session_state["historico_mensagens"]):
    with st.chat_message(msg["papel"]):
        st.write(msg["conteudo"])
        if msg.get("telemetria"):
            renderizar_telemetria(msg["telemetria"])
        if msg.get("voz"):
            renderizar_voz(msg["voz"])
        if msg["papel"] == "assistant" and msg.get("telemetria"):
            renderizar_exportacao(
                msg.get("pergunta", ""), msg["conteudo"], msg["telemetria"], f"md_{i}"
            )
        if msg["papel"] == "assistant" and (
            msg.get("registro") or (msg.get("telemetria") or {}).get("registro")
        ):
            renderizar_finalizacao(
                msg.get("registro") or msg["telemetria"]["registro"], f"historico_{i}"
            )

EXEMPLOS = [
    "De onde vem a maior parte dos clientes?",
    "Qual o faturamento por mês, sem contar notas canceladas?",
    "Quais notas estão vencidas e de quais clientes?",
    "Quais são os 5 clientes que mais compraram?",
]
if not st.session_state["historico_mensagens"]:
    with st.expander("Sugestões de pergunta"):
        colunas_ex = st.columns(2)
        for i, exemplo in enumerate(EXEMPLOS):
            if colunas_ex[i % 2].button(
                exemplo, key=f"exemplo_{i}", use_container_width=True
            ):
                st.session_state["pergunta_pendente"] = exemplo
                st.rerun()

comando_chat = st.chat_input("Pergunte sobre as evidências ou peça uma ação")
pergunta = comando_chat or st.session_state["pergunta_pendente"]
st.session_state["pergunta_pendente"] = None

if pergunta:
    st.session_state["historico_mensagens"].append(
        {"papel": "user", "conteudo": pergunta}
    )
    with st.chat_message("user"):
        st.write(pergunta)

    with st.chat_message("assistant"):

        def ao_evento(ev: dict):
            """Mostra cada passo do agente assim que acontece."""
            if ev["tipo"] == "turno":
                st.markdown(
                    f'<div class="passo"><span>▸</span> turno {ev["n"]}: modelo analisando</div>',
                    unsafe_allow_html=True,
                )
            elif ev["tipo"] == "ferramenta":
                falhou = "erro" in (ev["resultado"] or {})
                if ev["nome"] == "consultar_banco":
                    args = html.escape(
                        " ".join(str(ev["argumentos"].get("sql", "")).split())[:110]
                    )
                else:
                    args = html.escape(json.dumps(ev["argumentos"], ensure_ascii=False))
                st.markdown(
                    f'<div class="passo"><span>▸</span> <code>{html.escape(ev["nome"])}</code> {args} '
                    f'<em class="{"erro" if falhou else ""}">{"ERRO" if falhou else "OK"} · {ev["duracao_ms"]} ms</em></div>',
                    unsafe_allow_html=True,
                )

        try:
            with st.status(
                "Raciocinando e consultando ferramentas...", expanded=True
            ) as status:
                resultado = executar_agente(
                    pergunta,
                    st.session_state["evidencias_ativas"],
                    ao_evento=ao_evento,
                )
                status.update(
                    label="Análise concluída", state="complete", expanded=False
                )

            # A voz é preparada em paralelo enquanto o texto "digita".
            futuro_voz = None
            if voz_ativa:
                executor = ThreadPoolExecutor(max_workers=1)
                futuro_voz = executor.submit(
                    preparar_voz,
                    resultado["resposta"],
                    voz_escolhida,
                    tamanho_resumo,
                    estilo_voz,
                    ritmo_voz,
                )
                executor.shutdown(wait=False)

            st.write_stream(digitar(resultado["resposta"]))
            renderizar_telemetria(resultado)

            voz = None
            if futuro_voz:
                try:
                    with st.spinner("Preparando a voz..."):
                        voz = futuro_voz.result()
                    renderizar_voz(voz, autoplay=True)
                except Exception as e:
                    st.caption(f"Não foi possível gerar a voz: {e}")

            # Índice que a mensagem terá no histórico (calculado antes do append)
            idx_msg = len(st.session_state["historico_mensagens"])
            renderizar_exportacao(
                pergunta, resultado["resposta"], resultado, f"md_{idx_msg}"
            )
            # Chave estável: o mesmo painel reaparece do histórico no rerun do clique
            renderizar_finalizacao(resultado["registro"], f"historico_{idx_msg}")

            st.session_state["historico_mensagens"].append(
                {
                    "papel": "assistant",
                    "conteudo": resultado["resposta"],
                    "pergunta": pergunta,
                    "telemetria": resultado,
                    "registro": resultado["registro"],
                    "voz": voz,
                }
            )
        except Exception as e:
            erro = f"Falha na execução: {type(e).__name__} - {e}"
            st.error(erro)
            st.session_state["historico_mensagens"].append(
                {"papel": "assistant", "conteudo": erro}
            )

# Por último, para incluir também a resposta gerada neste mesmo run.
renderizar_exportacao_financeira(st.session_state["historico_mensagens"])
