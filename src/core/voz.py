"""Resposta por voz: resume a resposta longa e transforma o resumo em audio."""
import io
import os
import re
import wave

from google.genai import types

from src.core.config import MODEL, criar_cliente_gemini
from src.core.resiliencia import gerar_conteudo

# Tamanhos do resumo falado: (instrucao ao resumidor, limite de caracteres).
# Respostas ate o limite sao lidas inteiras, sem passar pelo resumidor.
TAMANHOS = {
    "Curto": ("uma unica frase curta (ate 140 caracteres), com a conclusao principal", 160),
    "Médio": ("no maximo 3 frases curtas (cerca de 250 caracteres), comecando pela conclusao", 280),
    "Detalhado": ("no maximo 5 frases curtas (cerca de 450 caracteres), comecando pela conclusao", 480),
}
TAMANHO_PADRAO = "Médio"

# Estilos de fala: instrucao em linguagem natural que antecede o texto.
ESTILOS = {
    "Mordomo digital": "com voz calma e elegante, tom polido e discreto, com um leve toque de ironia refinada, sem arrastar as palavras",
    "Padrão": "com voz clara e profissional",
    "Objetivo": "de forma direta e ágil, em tom neutro",
    "Caloroso": "com tom acolhedor e amigável",
}

# Ritmo da fala (o Gemini TTS nao tem controle numerico de velocidade; o ritmo vai na instrucao).
RITMOS = {
    "Natural": "em ritmo natural de conversa",
    "Ágil": "em ritmo ágil e fluido, sem pausas longas",
    "Rápido": "em ritmo rápido e dinâmico, sem pausas longas",
}

# Vozes pre-definidas do Gemini TTS (a primeira e a padrao).
VOZES = ["Charon", "Orus", "Kore", "Zephyr"]

# Os nomes dos modelos TTS mudam com frequencia. Defina MODELO_TTS no ambiente
# para fixar um; os demais servem de reserva, na ordem.
MODELOS_TTS = [
    m for m in (
        os.getenv("MODELO_TTS"),
        "gemini-3.1-flash-tts-preview",
        "gemini-2.5-flash-preview-tts",
    ) if m
]


def _instrucao_resumo(tamanho: str) -> str:
    regra, _ = TAMANHOS.get(tamanho, TAMANHOS[TAMANHO_PADRAO])
    return (
        "Voce transforma respostas escritas em um resumo para ser LIDO EM VOZ ALTA. "
        f"Regras: portugues brasileiro; {regra}; sem markdown, listas, emojis ou "
        "simbolos; escreva valores e datas de forma natural para fala; use apenas "
        "fatos presentes no texto, sem inventar nada; se o texto pedir confirmacao "
        "ou apontar divergencia, diga isso no resumo. Responda somente com o resumo."
    )


def _limpar_markdown(texto: str) -> str:
    texto = re.sub(r"[`*_#>]+", "", texto)
    texto = re.sub(r"^\s*[-•]\s+", "", texto, flags=re.MULTILINE)
    return re.sub(r"\s+", " ", texto).strip()


def _cortar_em_frase(texto: str, limite: int) -> str:
    if len(texto) <= limite:
        return texto
    corte = texto[:limite]
    ponto = max(corte.rfind(". "), corte.rfind("! "), corte.rfind("? "))
    return corte[: ponto + 1] if ponto > 80 else corte.rstrip() + "..."


def resumir_para_voz(texto: str, tamanho: str = TAMANHO_PADRAO) -> str:
    _, limite = TAMANHOS.get(tamanho, TAMANHOS[TAMANHO_PADRAO])
    limpo = _limpar_markdown(texto)
    if len(limpo) <= limite:
        return limpo

    try:
        cliente = criar_cliente_gemini()
        # Semáforo (8 simultâneas) + retry em 429/503 (1 s, 2 s, 4 s).
        resposta = gerar_conteudo(
            cliente,
            model=MODEL,
            contents=texto,
            config=types.GenerateContentConfig(
                system_instruction=_instrucao_resumo(tamanho),
                temperature=0.0,
            ),
        )
        resumo = _limpar_markdown(resposta.text or "")
        if resumo:
            return resumo
    except Exception:
        pass
    # Reserva: corta o texto original na ultima frase inteira.
    return _cortar_em_frase(limpo, limite)


def sintetizar_voz(texto: str, voz: str = VOZES[0], estilo: str = "Mordomo digital",
                   ritmo: str = "Ágil") -> bytes:
    """Gera audio WAV a partir do texto. Retorna os bytes do arquivo."""
    cliente = criar_cliente_gemini()
    ultimo_erro = None
    instrucao = ESTILOS.get(estilo, ESTILOS["Padrão"]) + ", " + RITMOS.get(ritmo, RITMOS["Ágil"])

    for modelo in MODELOS_TTS:
        try:
            resposta = gerar_conteudo(
                cliente,
                model=modelo,
                contents=f"Diga em português brasileiro, {instrucao}: {texto}",
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voz)
                        )
                    ),
                ),
            )
            partes = resposta.candidates[0].content.parts
            dado = next(
                p.inline_data for p in partes
                if p.inline_data and p.inline_data.data
            )
            # O Gemini devolve PCM cru (16 bits, mono); empacota como WAV.
            achou = re.search(r"rate=(\d+)", dado.mime_type or "")
            taxa = int(achou.group(1)) if achou else 24000
            buffer = io.BytesIO()
            with wave.open(buffer, "wb") as arquivo:
                arquivo.setnchannels(1)
                arquivo.setsampwidth(2)
                arquivo.setframerate(taxa)
                arquivo.writeframes(dado.data)
            return buffer.getvalue()
        except Exception as e:
            ultimo_erro = e

    raise RuntimeError(f"TTS indisponivel ({type(ultimo_erro).__name__}: {ultimo_erro})")


def preparar_voz(resposta: str, voz: str = VOZES[0], tamanho: str = TAMANHO_PADRAO,
                 estilo: str = "Mordomo digital", ritmo: str = "Ágil") -> dict:
    resumo = resumir_para_voz(resposta, tamanho)
    return {"resumo": resumo, "audio": sintetizar_voz(resumo, voz, estilo, ritmo)}