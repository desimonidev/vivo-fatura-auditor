import io
import os
import sqlite3
import tempfile
from datetime import datetime

import pandas as pd
import streamlit as st

from parser import ler_fatura_completa, _diagnosticar_diarias_travel
from auth import (
    init_auth_db,
    quantidade_usuarios,
    criar_usuario,
    autenticar,
    listar_usuarios,
    alternar_usuario,
)
from database import (
    DB_NAME,
    salvar_fatura,
    buscar_empresas,
    buscar_faturas_empresa,
    carregar_dados_fatura,
    normalizar_nome_empresa,
)


st.set_page_config(
    page_title="Auditoria de Faturas Vivo",
    page_icon="📱",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# ESTILO VISUAL
# ============================================================
st.markdown(
    """
    <style>
    :root {
        --bg: #080d1c;
        --panel: #111a2d;
        --panel-2: #17223a;
        --border: #263653;
        --text: #f2f5ff;
        --muted: #9ba9c6;
        --purple: #8b3dff;
        --pink: #d900b9;
        --green: #27d88a;
        --yellow: #f3c84b;
        --red: #ff6386;
    }

    .stApp {
        background: linear-gradient(135deg, #080d1c 0%, #0d1427 100%);
        color: var(--text);
    }

    [data-testid="stSidebar"] {
        background: #0d1325;
        border-right: 1px solid #202d49;
    }

    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
        color: #b7c3dc;
    }

    h1, h2, h3, h4 {
        color: var(--text) !important;
        letter-spacing: -0.02em;
    }

    .page-subtitle {
        color: var(--muted);
        margin-top: -12px;
        margin-bottom: 24px;
        font-size: 1rem;
    }

    .brand-title {
        font-size: 1.35rem;
        font-weight: 800;
        color: #ffffff;
        margin-top: 8px;
    }

    .brand-subtitle {
        color: #8e9bb7;
        line-height: 1.35;
        margin-bottom: 24px;
    }

    .section-title {
        color: #ffffff;
        font-size: 1.05rem;
        font-weight: 700;
        margin-bottom: 2px;
    }

    .section-caption {
        color: var(--muted);
        font-size: .85rem;
        margin-bottom: 16px;
    }

    .metric-card {
        min-height: 132px;
        padding: 20px;
        border: 1px solid var(--border);
        border-radius: 14px;
        background: linear-gradient(145deg, #16233e, #10182b);
        box-shadow: 0 8px 26px rgba(0,0,0,.18);
    }

    .metric-card.purple { background: linear-gradient(145deg, #20204d, #151b38); }
    .metric-card.pink { background: linear-gradient(145deg, #411c48, #21162f); }
    .metric-card.yellow { background: linear-gradient(145deg, #393225, #201d20); }

    .metric-label { color: #a9b6d1; font-size: .86rem; }
    .metric-value { color: #ffffff; font-size: 1.62rem; font-weight: 800; margin: 8px 0 2px; }
    .metric-note { color: #7c8eaf; font-size: .78rem; }
    .metric-icon { font-size: 1.45rem; margin-bottom: 5px; }

    .company-card {
        border: 1px solid var(--border);
        border-radius: 14px;
        padding: 16px;
        background: linear-gradient(145deg, #151f35, #10182a);
        min-height: 184px;
        margin-bottom: 12px;
    }

    .company-initial {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 40px;
        height: 40px;
        border-radius: 50%;
        background: linear-gradient(135deg, #8144ff, #cf14bd);
        color: white;
        font-size: 1.2rem;
        font-weight: 800;
        margin-right: 10px;
    }

    .company-name { font-weight: 800; color: white; font-size: 1.02rem; }
    .company-detail { color: #8494b2; font-size: .78rem; margin-top: 2px; }
    .company-count { color: #bbc6dc; font-size: .85rem; margin: 14px 0; }

    .status-ok {
        color: #73edb0;
        background: rgba(39,216,138,.15);
        border: 1px solid rgba(39,216,138,.25);
        border-radius: 20px;
        padding: 4px 10px;
        font-size: .78rem;
    }

    .status-warning {
        color: #f5d56a;
        background: rgba(243,200,75,.14);
        border: 1px solid rgba(243,200,75,.25);
        border-radius: 20px;
        padding: 4px 10px;
        font-size: .78rem;
    }

    .status-danger {
        color: #ff8aa2;
        background: rgba(255,99,134,.14);
        border: 1px solid rgba(255,99,134,.25);
        border-radius: 20px;
        padding: 4px 10px;
        font-size: .78rem;
    }

    .due-row {
        padding: 12px 0;
        border-bottom: 1px solid #23314d;
    }

    .due-date { color: #d7b7ff; font-weight: 800; font-size: .9rem; }
    .due-company { color: #eef2ff; font-weight: 600; }
    .due-ref { color: #8290ab; font-size: .75rem; }
    .due-value { color: #f4f6ff; font-weight: 700; text-align: right; }

    div[data-testid="stDataFrame"] {
        border: 1px solid var(--border);
        border-radius: 12px;
        overflow: hidden;
    }

    .block-container { padding-top: 2.1rem; padding-bottom: 3rem; }
    button[kind="primary"] {
        background: linear-gradient(90deg, #8c00ff, #d000b9) !important;
        border: none !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================
def moeda(valor) -> str:
    try:
        valor = float(valor or 0)
    except (TypeError, ValueError):
        valor = 0.0
    return (
        f"R$ {valor:,.2f}"
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )


def linha_sem_mascara(valor) -> str:
    """Retorna o número da linha somente com dígitos."""
    if valor is None:
        return "-"
    digitos = "".join(ch for ch in str(valor) if ch.isdigit())
    return digitos or "-"


def nome_curto(resultado: dict) -> str:
    razao = (
        resultado.get("razao_social_completa")
        or resultado.get("cliente")
        or "EMPRESA DESCONHECIDA"
    )
    return normalizar_nome_empresa(razao)


def preparar_resultado(resultado: dict) -> dict:
    resultado = dict(resultado or {})
    razao = (
        resultado.get("razao_social_completa")
        or resultado.get("cliente")
        or "EMPRESA DESCONHECIDA"
    )
    resultado["razao_social_completa"] = razao
    resultado["cliente"] = normalizar_nome_empresa(razao)
    return resultado


def segundos(duracao) -> int:
    if not isinstance(duracao, str) or "m" not in duracao:
        return 0
    try:
        minutos, resto = duracao.split("m", 1)
        return int(minutos) * 60 + int(resto.replace("s", ""))
    except (ValueError, TypeError):
        return 0


def dados_dashboard():
    """Consulta os indicadores diretamente, funcionando com o database atual."""
    try:
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS qtd, COALESCE(SUM(valor_total), 0) AS total FROM faturas")
        resumo = dict(cur.fetchone())
        cur.execute("SELECT COUNT(DISTINCT cliente) AS qtd FROM faturas")
        empresas = int(cur.fetchone()["qtd"] or 0)
        cur.execute(
            """
            SELECT id, cliente, mes_referencia, vencimento, valor_total, data_processamento
            FROM faturas
            ORDER BY id DESC
            LIMIT 10
            """
        )
        recentes = [dict(linha) for linha in cur.fetchall()]
        cur.execute(
            """
            SELECT cliente, mes_referencia, vencimento, valor_total
            FROM faturas
            WHERE vencimento IS NOT NULL AND vencimento <> '-'
            ORDER BY
                substr(vencimento, 7, 4),
                substr(vencimento, 4, 2),
                substr(vencimento, 1, 2)
            LIMIT 5
            """
        )
        vencimentos = [dict(linha) for linha in cur.fetchall()]
        conn.close()
        return {
            "empresas": empresas,
            "faturas": int(resumo.get("qtd") or 0),
            "total": float(resumo.get("total") or 0),
            "recentes": recentes,
            "vencimentos": vencimentos,
        }
    except Exception:
        return {"empresas": 0, "faturas": 0, "total": 0, "recentes": [], "vencimentos": []}


def status_vencimento(data):
    try:
        venc = datetime.strptime(data, "%d/%m/%Y").date()
        hoje = datetime.now().date()
        dias = (venc - hoje).days
        if dias < 0:
            return "Vencida", "status-danger"
        if dias <= 7:
            return "Próxima", "status-warning"
        return "Processada", "status-ok"
    except (ValueError, TypeError):
        return "Processada", "status-ok"


def botao_voltar(chave, destino):
    if st.button("← Voltar", key=chave, use_container_width=True):
        st.session_state.tela = destino
        st.session_state.empresa_selecionada = None
        st.session_state.fatura_selecionada_id = None
        st.rerun()


# ============================================================
# ABAS DA FATURA
# ============================================================
def renderizar_abas_fatura(resultado):
    resultado = preparar_resultado(resultado)
    boleto = resultado.get("boleto") or {}
    abas = st.tabs(["Resumo da Fatura", "Análise de Ligações", "Análise de Excedentes", "Relatório Geral", "Relatório de Ofensores"])

    with abas[0]:
        valor_total = boleto.get("total_pagar", resultado.get("soma_mensalidades", 0))
        linhas = resultado.get("linhas") or []
        c1, c2, c3 = st.columns(3)
        c1.metric("Quantidade de linhas", resultado.get("total_linhas", len(linhas)))
        c2.metric("Valor total", moeda(valor_total))
        if resultado.get("tem_parcelamento"):
            parcelamento = sum(
                linha.get("parcelamento", 0)
                for linha in linhas
                if isinstance(linha.get("parcelamento"), (int, float))
            )
            c3.metric("Parcelamentos", moeda(parcelamento))

        tabela = []
        for linha in linhas:
            tabela.append({
                "Número Vivo": linha_sem_mascara(linha.get("numero")),
                "Plano": linha.get("plano", "-"),
                "Mensalidade": linha.get("mensalidade", 0),
                "Consumo (GB)": linha.get("consumo_dados_gb", 0),
                "Pacote Travel": linha.get("pacote_travel_valor"),
                "Parcelamento": linha.get("parcelamento") if resultado.get("tem_parcelamento") else None,
                "Parcela": linha.get("parcela", "-") if resultado.get("tem_parcelamento") else "-",
            })
        df = pd.DataFrame(tabela)
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Mensalidade": st.column_config.NumberColumn(format="R$ %.2f"),
                "Consumo (GB)": st.column_config.NumberColumn(format="%.2f GB"),
                "Pacote Travel": st.column_config.NumberColumn(format="R$ %.2f"),
                "Parcelamento": st.column_config.NumberColumn(format="R$ %.2f"),
            },
        )

        st.divider()
        nfc, bol = st.columns(2)
        nf = resultado.get("maior_nfcom")
        with nfc:
            st.subheader("NFCOM principal")
            if nf:
                st.write(f"**NFCOM:** {nf.get('nfcom', '-')}")
                st.write(f"**Série:** {nf.get('serie', '-')}")
                st.write(f"**Emissão:** {nf.get('data_emissao', '-')}")
                st.write(f"**Valor:** {moeda(nf.get('valor_total'))}")
            else:
                st.info("Nenhuma NFCOM encontrada.")
        with bol:
            st.subheader("Boleto")
            st.write(f"**Vencimento:** {boleto.get('vencimento', '-')}")
            st.write(f"**Referência:** {boleto.get('mes_referencia', '-')}")
            st.write(f"**Ciclo:** {resultado.get('ciclo_fatura', '-')}")
            st.write(f"**Total a pagar:** {moeda(boleto.get('total_pagar'))}")

        with st.expander("Identificação completa da empresa"):
            st.write(f"**Nome exibido:** {resultado.get('cliente', '-')}")
            st.write(f"**Razão social:** {resultado.get('razao_social_completa', '-')}")

    with abas[1]:
        ligacoes = resultado.get("ligacoes") or []
        if not ligacoes:
            st.info("Nenhuma ligação encontrada no PDF.")
        else:
            df = pd.DataFrame(ligacoes)
            if "linha_origem" in df.columns:
                df["linha_origem"] = df["linha_origem"].apply(linha_sem_mascara)
            if "numero_destino" in df.columns:
                df["numero_destino"] = df["numero_destino"].apply(linha_sem_mascara)
            c1, c2, c3 = st.columns(3)
            with c1:
                saida = st.multiselect("Linha de origem", sorted(df["linha_origem"].unique()), key="f_saida")
            with c2:
                data = st.multiselect("Data", sorted(df["data"].unique()), key="f_data")
            with c3:
                secao = st.multiselect("Seção", sorted(df["secao"].unique()), key="f_secao")
            if saida:
                df = df[df["linha_origem"].isin(saida)]
            if data:
                df = df[df["data"].isin(data)]
            if secao:
                df = df[df["secao"].isin(secao)]
            df = df.copy()
            df["_segundos"] = df["duracao"].apply(segundos)
            st.dataframe(
                df.drop(columns=["_segundos"]),
                use_container_width=True,
                hide_index=True,
                column_config={"valor": st.column_config.NumberColumn(format="R$ %.2f")},
            )
            resumo = df.groupby("linha_origem").agg(
                quantidade=("numero_destino", "size"),
                duracao_total_segundos=("_segundos", "sum"),
                valor_total=("valor", "sum"),
            ).reset_index()
            with st.expander("Resumo por linha e exportação"):
                st.dataframe(resumo, use_container_width=True, hide_index=True)
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                    df.drop(columns=["_segundos"]).to_excel(writer, index=False, sheet_name="Ligações")
                    resumo.to_excel(writer, index=False, sheet_name="Resumo")
                st.download_button(
                    "Baixar Excel",
                    buffer.getvalue(),
                    "ligacoes_vivo.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

    with abas[2]:
        diarias = resultado.get("excedentes_diarias") or []
        excedentes = resultado.get("excedentes_ligacoes") or []
        if not diarias and not excedentes:
            st.success("Nenhum excedente ou serviço adicional encontrado.")
        if diarias:
            st.subheader("Diárias Vivo Travel")
            st.caption("A/E = Américas/Europa: R$ 39,99 por dia · Mundo: R$ 59,99 por dia")
            agrupado = {}
            detalhadas = []

            for item in diarias:
                linha = linha_sem_mascara(item.get("linha"))
                valor = float(item.get("valor", 0) or 0)
                diagnostico = _diagnosticar_diarias_travel(valor)
                regiao = "Não identificada"
                if diagnostico and diagnostico.get("possibilidades"):
                    possibilidade = diagnostico["possibilidades"][0]
                    qtd_ae = possibilidade.get("americas_europa", 0)
                    qtd_mundo = possibilidade.get("mundo", 0)
                    if qtd_ae > 0 and qtd_mundo > 0:
                        regiao = "Mista"
                    elif qtd_mundo > 0:
                        regiao = "Mundo"
                    elif qtd_ae > 0:
                        regiao = "A/E"

                agrupado.setdefault(linha, {
                    "Linha": linha,
                    "Dias": 0,
                    "A/E": 0,
                    "Mundo": 0,
                    "Não identificadas": 0,
                    "Valor total": 0.0,
                })
                agrupado[linha]["Dias"] += 1
                agrupado[linha]["Valor total"] += valor
                if regiao in {"A/E", "Mundo", "Não identificada"}:
                    agrupado[linha][regiao] += 1

                detalhadas.append({
                    "Linha": linha,
                    "Data": item.get("data", "-"),
                    "Quantidade": item.get("quantidade", "-"),
                    "Região": regiao,
                    "Valor": valor,
                })

            st.dataframe(
                pd.DataFrame(list(agrupado.values())),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Valor total": st.column_config.NumberColumn(format="R$ %.2f"),
                },
            )
            with st.expander("Detalhamento das diárias"):
                st.dataframe(
                    pd.DataFrame(detalhadas),
                    use_container_width=True,
                    hide_index=True,
                    column_config={"Valor": st.column_config.NumberColumn(format="R$ %.2f")},
                )
        if excedentes:
            st.subheader("Ligações excedentes")
            df = pd.DataFrame(excedentes)
            if "linha" in df.columns:
                df["linha"] = df["linha"].apply(linha_sem_mascara)
            resumo = df.groupby("linha").agg(
                quantidade=("servico", "count"), valor_total=("valor", "sum")
            ).reset_index()
            st.dataframe(
                resumo,
                use_container_width=True,
                hide_index=True,
                column_config={"valor_total": st.column_config.NumberColumn(format="R$ %.2f")},
            )
            with st.expander("Detalhamento das ligações excedentes"):
                st.dataframe(df, use_container_width=True, hide_index=True)

    with abas[3]:
        renderizar_relatorio_geral(resultado)

    with abas[4]:
        renderizar_relatorio_ofensores(resultado)


# ============================================================
# RELATÓRIO GERAL DA CONTA
# ============================================================
def renderizar_relatorio_geral(resultado):
    """Consolida os principais valores da conta por linha."""
    linhas = resultado.get("linhas") or []
    ligacoes = resultado.get("excedentes_ligacoes") or []
    diarias = resultado.get("excedentes_diarias") or []

    dados = {}
    for item in linhas:
        numero = linha_sem_mascara(item.get("numero"))
        dados.setdefault(numero, {
            "Linha": numero,
            "Mensalidade": 0.0,
            "Pacote Travel": 0.0,
            "Parcelamento": 0.0,
            "Ligações excedentes": 0.0,
            "Diárias excedentes": 0.0,
        })
        dados[numero]["Mensalidade"] += float(item.get("mensalidade", 0) or 0)
        dados[numero]["Pacote Travel"] += float(item.get("pacote_travel_valor", 0) or 0)
        dados[numero]["Parcelamento"] += float(item.get("parcelamento", 0) or 0)

    for item in ligacoes:
        numero = linha_sem_mascara(item.get("linha"))
        dados.setdefault(numero, {"Linha": numero, "Mensalidade": 0.0, "Pacote Travel": 0.0, "Parcelamento": 0.0, "Ligações excedentes": 0.0, "Diárias excedentes": 0.0})
        dados[numero]["Ligações excedentes"] += float(item.get("valor", 0) or 0)

    for item in diarias:
        numero = linha_sem_mascara(item.get("linha"))
        dados.setdefault(numero, {"Linha": numero, "Mensalidade": 0.0, "Pacote Travel": 0.0, "Parcelamento": 0.0, "Ligações excedentes": 0.0, "Diárias excedentes": 0.0})
        dados[numero]["Diárias excedentes"] += float(item.get("valor", 0) or 0)

    st.subheader("Relatório geral da conta")
    st.caption("Visão consolidada dos valores identificados por linha nesta fatura. O total por linha é uma composição dos itens extraídos do PDF.")
    if not dados:
        st.info("Nenhuma linha foi encontrada nesta fatura.")
        return

    tabela = pd.DataFrame(list(dados.values()))
    colunas_valor = ["Mensalidade", "Pacote Travel", "Parcelamento", "Ligações excedentes", "Diárias excedentes"]
    tabela["Total composto"] = tabela[colunas_valor].sum(axis=1)
    tabela = tabela.sort_values("Total composto", ascending=False)

    total_conta = float(resultado.get("boleto", {}).get("total_pagar", 0) or 0)
    total_composto = float(tabela["Total composto"].sum())
    maior = tabela.iloc[0]
    c1, c2, c3 = st.columns(3)
    c1.metric("Linhas na conta", len(tabela))
    c2.metric("Total composto", moeda(total_composto))
    c3.metric("Maior valor por linha", moeda(maior["Total composto"]))
    if total_conta:
        st.caption(f"Total do boleto: {moeda(total_conta)} · Diferença para o total composto: {moeda(total_conta - total_composto)}")

    grafico = tabela.set_index("Linha")[["Total composto"]]
    st.bar_chart(grafico, height=360, use_container_width=True)
    st.dataframe(
        tabela,
        use_container_width=True,
        hide_index=True,
        column_config={coluna: st.column_config.NumberColumn(format="R$ %.2f") for coluna in colunas_valor + ["Total composto"]},
    )


# ============================================================
# RELATÓRIO RÁPIDO DE LINHAS OFENSORAS
# ============================================================
def renderizar_relatorio_ofensores(resultado):
    registros = []
    for item in resultado.get("excedentes_ligacoes") or []:
        registros.append({"Linha": linha_sem_mascara(item.get("linha")), "Tipo": "Ligação excedente", "Valor": float(item.get("valor", 0) or 0)})
    for item in resultado.get("excedentes_diarias") or []:
        registros.append({"Linha": linha_sem_mascara(item.get("linha")), "Tipo": "Diária Vivo Travel", "Valor": float(item.get("valor", 0) or 0)})
    st.subheader("Linha ofensora da fatura")
    st.caption("Ranking das linhas que geraram maior valor em cobranças excedentes nesta fatura.")
    if not registros:
        st.success("Nenhuma cobrança excedente foi encontrada nesta fatura.")
        return
    df = pd.DataFrame(registros)
    ranking = (df.groupby("Linha", as_index=False).agg(valor_total=("Valor", "sum"), quantidade_cobrancas=("Valor", "size")).sort_values("valor_total", ascending=False))
    maior = ranking.iloc[0]
    c1, c2, c3 = st.columns(3)
    c1.metric("Maior linha ofensora", str(maior["Linha"]))
    c2.metric("Valor da linha", moeda(maior["valor_total"]))
    c3.metric("Cobranças da linha", int(maior["quantidade_cobrancas"]))
    grafico = ranking.set_index("Linha")[["valor_total"]].rename(columns={"valor_total": "Valor excedente (R$)"})
    st.bar_chart(grafico, height=360, use_container_width=True)
    tabela = ranking.rename(columns={"valor_total": "Valor total (R$)", "quantidade_cobrancas": "Quantidade de cobranças"})
    st.dataframe(tabela, use_container_width=True, hide_index=True, column_config={"Valor total (R$)": st.column_config.NumberColumn(format="R$ %.2f")})
    with st.expander("Ver composição por tipo de cobrança"):
        por_tipo = (df.groupby(["Linha", "Tipo"], as_index=False).agg(valor_total=("Valor", "sum"), quantidade=("Valor", "size")).rename(columns={"valor_total": "Valor total (R$)", "quantidade": "Quantidade"}))
        st.dataframe(por_tipo, use_container_width=True, hide_index=True, column_config={"Valor total (R$)": st.column_config.NumberColumn(format="R$ %.2f")})


# ============================================================
# AUTENTICAÇÃO E USUÁRIOS
# ============================================================
def tela_login():
    st.markdown("<div style='max-width:480px;margin:8vh auto 0;'>", unsafe_allow_html=True)
    st.markdown("# vivo")
    st.title("Auditoria de Faturas")

    if quantidade_usuarios() == 0:
        st.info("Primeiro acesso: crie o usuário administrador do sistema.")
        with st.form("form_primeiro_admin"):
            nome = st.text_input("Nome completo")
            usuario = st.text_input("Usuário")
            senha = st.text_input("Senha", type="password", help="Mínimo de 6 caracteres")
            confirmar = st.text_input("Confirmar senha", type="password")
            criar = st.form_submit_button("Criar administrador", type="primary", use_container_width=True)
        if criar:
            if senha != confirmar:
                st.error("As senhas não conferem.")
            else:
                sucesso, mensagem = criar_usuario(nome, usuario, senha, "admin")
                if sucesso:
                    st.success("Administrador criado. Faça login para continuar.")
                    st.rerun()
                else:
                    st.error(mensagem)
    else:
        st.caption("Entre com seu usuário e senha para acessar o sistema.")
        with st.form("form_login"):
            usuario = st.text_input("Usuário", autocomplete="username")
            senha = st.text_input("Senha", type="password", autocomplete="current-password")
            entrar = st.form_submit_button("Entrar", type="primary", use_container_width=True)
        if entrar:
            usuario_logado = autenticar(usuario, senha)
            if usuario_logado:
                st.session_state.usuario_logado = usuario_logado
                st.session_state.tela = "Visão geral"
                st.rerun()
            else:
                st.error("Usuário ou senha inválidos.")
    st.markdown("</div>", unsafe_allow_html=True)


def tela_configuracoes():
    usuario_logado = st.session_state.get("usuario_logado") or {}
    if usuario_logado.get("perfil") != "admin":
        st.error("Apenas administradores podem acessar as configurações.")
        return

    st.title("Configurações")
    st.markdown('<div class="page-subtitle">Gerencie os usuários autorizados a acessar o sistema.</div>', unsafe_allow_html=True)
    aba_criar, aba_usuarios = st.tabs(["Criar usuário", "Usuários cadastrados"])

    with aba_criar:
        with st.form("form_novo_usuario"):
            nome = st.text_input("Nome completo")
            usuario = st.text_input("Nome de usuário")
            senha = st.text_input("Senha", type="password", help="Mínimo de 6 caracteres")
            confirmar = st.text_input("Confirmar senha", type="password")
            perfil = st.selectbox("Perfil", ["usuario", "admin"], format_func=lambda x: "Administrador" if x == "admin" else "Usuário")
            criar = st.form_submit_button("Criar usuário", type="primary")
        if criar:
            if senha != confirmar:
                st.error("As senhas não conferem.")
            else:
                sucesso, mensagem = criar_usuario(nome, usuario, senha, perfil)
                if sucesso:
                    st.success(mensagem)
                    st.rerun()
                else:
                    st.error(mensagem)

    with aba_usuarios:
        usuarios = listar_usuarios()
        if not usuarios:
            st.info("Nenhum usuário cadastrado.")
        else:
            for item in usuarios:
                coluna_info, coluna_status, coluna_acao = st.columns([3, 1, 1])
                with coluna_info:
                    perfil_label = "Administrador" if item["perfil"] == "admin" else "Usuário"
                    st.write(f"**{item['nome']}** · @{item['usuario']}")
                    st.caption(f"{perfil_label} · Criado em {item['criado_em']}")
                with coluna_status:
                    st.write("Ativo" if item["ativo"] else "Bloqueado")
                with coluna_acao:
                    eh_eu = item["id"] == usuario_logado.get("id")
                    if eh_eu:
                        st.caption("Seu usuário")
                    else:
                        texto = "Bloquear" if item["ativo"] else "Ativar"
                        if st.button(texto, key=f"alternar_usuario_{item['id']}"):
                            alternar_usuario(item["id"], not bool(item["ativo"]))
                            st.rerun()
                st.divider()


init_auth_db()
if "usuario_logado" not in st.session_state:
    st.session_state.usuario_logado = None

if not st.session_state.usuario_logado:
    tela_login()
    st.stop()

# ============================================================
# TELAS
# ============================================================
def tela_visao_geral():
    dados = dados_dashboard()
    st.title("Visão geral")
    st.markdown(
        '<div class="page-subtitle">Acompanhe o status das suas faturas e mantenha o controle dos seus gastos com telecomunicações.</div>',
        unsafe_allow_html=True,
    )

    col_btn, _ = st.columns([1, 3])
    with col_btn:
        if st.button("＋ Processar nova fatura", type="primary", use_container_width=True):
            st.session_state.tela = "Processar fatura"
            st.rerun()

    c1, c2, c3, c4 = st.columns(4)
    cards = [
        (c1, "🏢", "Empresas cadastradas", dados["empresas"], "empresas"),
        (c2, "▣", "Faturas processadas", dados["faturas"], "purple"),
        (c3, "◎", "Total processado", moeda(dados["total"]), "pink"),
        (c4, "▣", "Próximos vencimentos", len(dados["vencimentos"]), "yellow"),
    ]
    for coluna, icone, label, valor, classe in cards:
        with coluna:
            st.markdown(
                f'<div class="metric-card {classe if classe != "empresas" else ""}">'
                f'<div class="metric-icon">{icone}</div><div class="metric-label">{label}</div>'
                f'<div class="metric-value">{valor}</div><div class="metric-note">Atualizado agora</div></div>',
                unsafe_allow_html=True,
            )

    st.write("")
    esquerda, direita = st.columns([1.65, 1])
    with esquerda:
        st.markdown('<div class="section-title">Empresas</div><div class="section-caption">Empresas cadastradas no sistema</div>', unsafe_allow_html=True)
        empresas = buscar_empresas()
        if not empresas:
            st.info("Nenhuma empresa cadastrada ainda.")
        else:
            cards_empresas = st.columns(min(3, len(empresas)))
            for i, (empresa, qtd) in enumerate(empresas[:6]):
                with cards_empresas[i % len(cards_empresas)]:
                    inicial = empresa[:1].upper() if empresa else "?"
                    st.markdown(
                        f'<div class="company-card"><span class="company-initial">{inicial}</span>'
                        f'<span class="company-name">{empresa}</span>'
                        f'<div class="company-count">▤ {qtd} fatura(s) processada(s)</div></div>',
                        unsafe_allow_html=True,
                    )
                    if st.button("Ver faturas →", key=f"home_empresa_{i}_{empresa}", use_container_width=True):
                        st.session_state.empresa_selecionada = empresa
                        st.session_state.tela = "Empresa"
                        st.rerun()

    with direita:
        st.markdown('<div class="section-title">Próximos vencimentos</div><div class="section-caption">Faturas cadastradas no sistema</div>', unsafe_allow_html=True)
        if not dados["vencimentos"]:
            st.info("Nenhum vencimento encontrado.")
        else:
            for item in dados["vencimentos"]:
                st.markdown(
                    f'<div class="due-row"><div class="due-date">{item["vencimento"]}</div>'
                    f'<div class="due-company">{item["cliente"]}</div>'
                    f'<div class="due-ref">Referência {item["mes_referencia"]}</div>'
                    f'<div class="due-value">{moeda(item["valor_total"])}</div></div>',
                    unsafe_allow_html=True,
                )

    st.write("")
    st.markdown('<div class="section-title">Faturas recentes</div><div class="section-caption">Últimas faturas processadas no sistema</div>', unsafe_allow_html=True)
    if dados["recentes"]:
        tabela = []
        for item in dados["recentes"]:
            status, _ = status_vencimento(item["vencimento"])
            tabela.append({
                "Empresa": item["cliente"],
                "Mês de referência": item["mes_referencia"],
                "Vencimento": item["vencimento"],
                "Valor": item["valor_total"],
                "Status": status,
            })
        st.dataframe(
            pd.DataFrame(tabela),
            use_container_width=True,
            hide_index=True,
            column_config={"Valor": st.column_config.NumberColumn(format="R$ %.2f")},
        )
    else:
        st.info("Nenhuma fatura processada ainda.")


def tela_processar():
    st.title("Processar nova fatura")
    st.markdown('<div class="page-subtitle">Envie uma fatura Vivo em PDF para iniciar a auditoria.</div>', unsafe_allow_html=True)
    arquivo = st.file_uploader("Escolha a fatura (PDF)", type=["pdf"])

    if "resultado" not in st.session_state:
        st.session_state.resultado = None
    if "arquivo_hash" not in st.session_state:
        st.session_state.arquivo_hash = None

    if arquivo:
        atual = hash(arquivo.getvalue())
        if atual != st.session_state.arquivo_hash:
            st.session_state.resultado = None
            st.session_state.arquivo_hash = atual

        if st.button("Processar fatura", type="primary"):
            caminho = None
            with st.spinner("Lendo e analisando o PDF..."):
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                    tmp.write(arquivo.getvalue())
                    caminho = tmp.name
                try:
                    resultado = preparar_resultado(ler_fatura_completa(caminho))
                    st.session_state.resultado = resultado
                    salvou = salvar_fatura(resultado)
                    empresa = resultado.get("cliente", "EMPRESA DESCONHECIDA")
                    razao = resultado.get("razao_social_completa", empresa)
                    if salvou:
                        st.success(f"Fatura da empresa **{empresa}** salva com sucesso!")
                    else:
                        st.warning(f"Fatura da empresa **{empresa}** já existe no banco de dados.")
                    if razao != empresa:
                        st.caption(f"Razão social identificada: {razao}")
                except Exception as erro:
                    st.error(f"Erro ao processar a fatura: {erro}")
                finally:
                    if caminho and os.path.exists(caminho):
                        os.unlink(caminho)

    if st.session_state.resultado:
        st.divider()
        renderizar_abas_fatura(st.session_state.resultado)


def tela_empresas():
    if st.session_state.empresa_selecionada is None:
        st.title("Empresas")
        st.markdown('<div class="page-subtitle">Entre em uma empresa para acessar todas as faturas processadas.</div>', unsafe_allow_html=True)
        empresas = buscar_empresas()
        if not empresas:
            st.info("Nenhuma fatura processada ainda.")
            return
        colunas = st.columns(3)
        for i, (empresa, qtd) in enumerate(empresas):
            with colunas[i % 3]:
                st.markdown(
                    f'<div class="company-card"><span class="company-initial">{empresa[:1]}</span>'
                    f'<span class="company-name">{empresa}</span>'
                    f'<div class="company-count">▤ {qtd} fatura(s) processada(s)</div></div>',
                    unsafe_allow_html=True,
                )
                if st.button("Acessar empresa", key=f"empresa_{i}_{empresa}", use_container_width=True):
                    st.session_state.empresa_selecionada = empresa
                    st.rerun()
        return

    empresa = st.session_state.empresa_selecionada
    col1, col2 = st.columns([1, 5])
    with col1:
        botao_voltar("voltar_empresas", "Empresas")
    with col2:
        st.title(f"Faturas de {empresa}")
    filtro = st.text_input("Filtrar por vencimento", placeholder="Ex.: 10/2026")
    faturas = buscar_faturas_empresa(empresa, filtro or None)
    if not faturas:
        st.warning("Nenhuma fatura encontrada para este filtro.")
        return

    tabela = []
    for fatura in faturas:
        status, _ = status_vencimento(fatura["vencimento"])
        tabela.append({
            "Mês de referência": fatura["mes_referencia"],
            "Vencimento": fatura["vencimento"],
            "Valor": fatura["valor_total"],
            "Processado em": fatura["data_processamento"],
            "Status": status,
        })
    st.dataframe(
        pd.DataFrame(tabela),
        use_container_width=True,
        hide_index=True,
        column_config={"Valor": st.column_config.NumberColumn(format="R$ %.2f")},
    )

    opcoes = {
        f"{item['vencimento']} · Ref. {item['mes_referencia']} · {moeda(item['valor_total'])}": item["id"]
        for item in faturas
    }
    escolha = st.selectbox("Selecione uma fatura para auditar", list(opcoes.keys()))
    if st.button("Abrir auditoria", type="primary"):
        st.session_state.fatura_selecionada_id = opcoes[escolha]
        st.session_state.tela = "Detalhes"
        st.rerun()


def tela_detalhes():
    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("← Voltar", key="voltar_detalhes", use_container_width=True):
            st.session_state.fatura_selecionada_id = None
            st.session_state.tela = "Empresa"
            st.rerun()
    with col2:
        st.title("Detalhes da fatura")
    dados = carregar_dados_fatura(st.session_state.fatura_selecionada_id)
    if not dados:
        st.error("Não foi possível carregar os dados da fatura.")
        return
    dados = preparar_resultado(dados)
    boleto = dados.get("boleto") or {}
    st.info(
        f"**Empresa:** {dados.get('cliente', '-')}  ·  "
        f"**Vencimento:** {boleto.get('vencimento', '-')}  ·  "
        f"**Referência:** {boleto.get('mes_referencia', '-')}"
    )
    renderizar_abas_fatura(dados)


# ============================================================
# NAVEGAÇÃO
# ============================================================
if "tela" not in st.session_state:
    st.session_state.tela = "Visão geral"
if "empresa_selecionada" not in st.session_state:
    st.session_state.empresa_selecionada = None
if "fatura_selecionada_id" not in st.session_state:
    st.session_state.fatura_selecionada_id = None

with st.sidebar:
    st.markdown("# vivo")
    st.markdown('<div class="brand-title">Auditoria de Faturas</div><div class="brand-subtitle">Mais controle para<br>sua empresa</div>', unsafe_allow_html=True)
    st.markdown("---")
    usuario_logado = st.session_state.usuario_logado
    opcoes_menu = ["Visão geral", "Empresas", "Processar fatura", "Relatórios"]
    if usuario_logado.get("perfil") == "admin":
        opcoes_menu.append("Configurações")

    # As telas Empresa e Detalhes pertencem ao menu Empresas.
    # Sem esta conversão, o radio da sidebar sobrescreve Detalhes
    # durante o st.rerun() e devolve o usuário para a tela inicial.
    tela_menu_atual = st.session_state.tela
    if tela_menu_atual in {"Empresa", "Detalhes"}:
        tela_menu_atual = "Empresas"

    tela_menu = st.radio(
        "Navegação",
        opcoes_menu,
        index=opcoes_menu.index(tela_menu_atual) if tela_menu_atual in opcoes_menu else 0,
    )

    if tela_menu != tela_menu_atual and tela_menu != "Relatórios":
        st.session_state.tela = tela_menu
        st.session_state.empresa_selecionada = None
        st.session_state.fatura_selecionada_id = None
        st.rerun()
    if tela_menu == "Relatórios":
        st.info("Relatórios avançados serão adicionados em uma próxima etapa.")
    st.markdown("---")
    st.markdown(f"**{usuario_logado.get('nome', 'Usuário')}**")
    st.caption(f"Perfil: {'Administrador' if usuario_logado.get('perfil') == 'admin' else 'Usuário'}")
    if st.button("Sair", use_container_width=True):
        st.session_state.usuario_logado = None
        st.session_state.tela = "Visão geral"
        st.rerun()
    st.markdown("---")
    st.caption("Sistema")
    st.caption("Auditoria Vivo")
    st.caption("v1.0.0")

if st.session_state.tela == "Visão geral":
    tela_visao_geral()
elif st.session_state.tela == "Empresas" or st.session_state.tela == "Empresa":
    tela_empresas()
elif st.session_state.tela == "Processar fatura":
    tela_processar()
elif st.session_state.tela == "Detalhes":
    tela_detalhes()
elif st.session_state.tela == "Relatórios":
    st.title("Relatórios")
    st.info("Módulo de relatórios em preparação.")
elif st.session_state.tela == "Configurações":
    tela_configuracoes()
