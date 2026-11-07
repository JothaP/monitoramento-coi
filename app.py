"""SAI — aviso definitivo de migração para o PRISMA.

A antiga página inicial foi substituída por um comunicado público.
Não apresenta login, hub, cartões de módulos ou comandos de acesso ao SAI.
Observação: o bloqueio de links diretos para as antigas páginas depende
igualmente da retirada/desativação dessas páginas no aplicativo legado.
"""

import streamlit as st


PRISMA_URL = "https://prisma-coi.streamlit.app"
DATA_DESCONTINUACAO = "07/11/2026"

st.set_page_config(
    page_title="SAI migrou para o PRISMA | COI",
    page_icon="💧",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
        /* O SAI não oferece mais menu de módulos nem navegação pela página inicial. */
        [data-testid="stSidebarNav"], [data-testid="stSidebar"],
        [data-testid="collapsedControl"] { display: none !important; }

        [data-testid="stAppViewContainer"], .stApp {
            background: #f2f6fb !important;
            color: #20334d !important;
        }
        [data-testid="stHeader"] { background: transparent !important; }
        .block-container {
            max-width: 840px !important;
            padding-top: clamp(3rem, 8vh, 7rem) !important;
            padding-bottom: 3rem !important;
        }
        .sai-migracao {
            border: 1px solid #dae6f0;
            border-radius: 24px;
            background: #ffffff;
            box-shadow: 0 16px 45px rgba(15, 56, 95, .07);
            overflow: hidden;
        }
        .sai-migracao-faixa {
            height: 9px;
            background: linear-gradient(90deg, #103a77 0%, #166eb1 55%, #0ac4c9 100%);
        }
        .sai-migracao-conteudo { padding: clamp(25px, 5vw, 48px); }
        .sai-etiqueta {
            display: inline-block;
            color: #075f74;
            font-size: .75rem;
            font-weight: 800;
            letter-spacing: .09em;
            margin-bottom: 16px;
        }
        .sai-titulo {
            color: #103a77;
            font-size: clamp(1.9rem, 4vw, 2.75rem);
            font-weight: 800;
            line-height: 1.18;
            letter-spacing: -.03em;
            margin: 0 0 18px;
        }
        .sai-descricao {
            color: #405873;
            font-size: 1.02rem;
            line-height: 1.75;
            margin: 0 0 20px;
        }
        .sai-status {
            display: block;
            border-left: 4px solid #0799ac;
            border-radius: 8px;
            background: #ecf8fb;
            color: #174563;
            padding: 13px 16px;
            line-height: 1.5;
            margin: 0 0 20px;
        }
        .sai-subtitulo {
            color: #103a77;
            font-size: 1.06rem;
            font-weight: 800;
            margin: 26px 0 6px;
        }
        .sai-ajuda {
            color: #61758b;
            font-size: .92rem;
            line-height: 1.65;
            margin: 0;
        }
        .sai-rodape {
            text-align: center;
            color: #61758b;
            font-size: .8rem;
            margin: 28px 0 0;
        }
        div[data-testid="stLinkButton"] a {
            background: #124e83 !important;
            color: white !important;
            border: 1px solid #124e83 !important;
            border-radius: 12px !important;
            min-height: 48px;
            font-weight: 700;
        }
        div[data-testid="stLinkButton"] a:hover {
            background: #0c7993 !important;
            border-color: #0c7993 !important;
            color: white !important;
        }
        div[data-testid="stLinkButton"] a * { color: white !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    f"""
    <section class="sai-migracao">
        <div class="sai-migracao-faixa"></div>
        <div class="sai-migracao-conteudo">
            <div class="sai-etiqueta">COMUNICADO OFICIAL · COI</div>
            <h1 class="sai-titulo">O SAI migrou para o PRISMA</h1>
            <p class="sai-descricao">
                O <strong>SAI — Sistema de Análises Integradas</strong> foi
                descontinuado. A plataforma foi substituída pelo
                <strong>PRISMA — Plataforma de Recursos Integrados para Suporte,
                Monitoramento e Análises</strong>, o novo ambiente de
                Inteligência Operacional Integrada do COI.
            </p>
            <div class="sai-status">
                <strong>SAI descontinuado desde {DATA_DESCONTINUACAO}.</strong><br>
                Para continuar utilizando as ferramentas operacionais,
                acesse o PRISMA pelo botão abaixo.
            </div>
        </div>
    </section>
    """,
    unsafe_allow_html=True,
)

st.link_button(
    "🔗 Acessar PRISMA",
    PRISMA_URL,
    type="primary",
    use_container_width=True,
)

st.markdown(
    """
    <div class="sai-subtitulo">Primeiro acesso ao PRISMA</div>
    <p class="sai-ajuda">
        Caso ainda não tenha uma conta, selecione <strong>Criar conta</strong> na
        página de acesso do PRISMA, utilize seu e-mail corporativo e siga as
        instruções de confirmação. O acesso aos módulos depende das
        permissões concedidas no novo sistema.
    </p>
    <div class="sai-rodape">
        COI — Centro de Operações Integradas<br>
        SAI — Sistema de Análises Integradas · Plataforma descontinuada
    </div>
    """,
    unsafe_allow_html=True,
)

# O app.py legado termina nesta página: não renderizar login nem hub.
st.stop()
