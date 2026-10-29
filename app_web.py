import streamlit as st
import pandas as pd
import tempfile
import os
import io
from parser import ler_fatura_completa

st.set_page_config(page_title="Auditor Vivo", page_icon="📱", layout="wide")
st.title("📱 Auditor de Faturas Vivo")

# ---------- Estado persistente ----------
if "resultado" not in st.session_state:
    st.session_state.resultado = None
if "arquivo_hash" not in st.session_state:
    st.session_state.arquivo_hash = None

arquivo_pdf = st.file_uploader("Escolha a fatura (PDF)", type=["pdf"])

if arquivo_pdf is not None:
    # Detecta troca de arquivo (hash simples)
    hash_atual = hash(arquivo_pdf.getvalue())
    if st.session_state.arquivo_hash != hash_atual:
        st.session_state.resultado = None
        st.session_state.arquivo_hash = hash_atual

    if st.button("Processar Fatura", type="primary"):
        with st.spinner("Lendo o PDF. Isso pode levar alguns segundos..."):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(arquivo_pdf.getvalue())
                caminho_tmp = tmp.name
            try:
                st.session_state.resultado = ler_fatura_completa(caminho_tmp)
            except Exception as e:
                st.error(f"Erro ao processar: {e}")
            finally:
                if os.path.exists(caminho_tmp):
                    os.unlink(caminho_tmp)

# ---------- Renderiza resultado guardado ----------
resultado = st.session_state.resultado
if resultado is not None:
    aba_fatura, aba_ligacoes = st.tabs(["📄 Resumo da Fatura", "📞 Análise de Ligações"])

    # ---------- ABA 1: FATURA ----------
    with aba_fatura:
        col1, col2 = st.columns(2)
        col1.metric("Total de Números", resultado["total_linhas"])
        col2.metric("Valor Total (R$)", f"{resultado['soma_mensalidades']:.2f}")

        df_fatura = pd.DataFrame(resultado["linhas"]).rename(columns={
            "numero": "Número Vivo", "plano": "Plano",
            "mensalidade": "Mensalidade (R$)", "consumo_dados_gb": "Consumo (GB)",
            "travel": "Travel (R$)", "pacote_travel": "Pacote Travel",
        })
        st.dataframe(df_fatura, use_container_width=True, hide_index=True, column_config={
            "Mensalidade (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
            "Consumo (GB)": st.column_config.NumberColumn(format="%.2f GB"),
        })

    # ---------- ABA 2: LIGAÇÕES ----------
    with aba_ligacoes:
        if not resultado["ligacoes"]:
            st.warning("Nenhuma ligação encontrada no PDF.")
        else:
            df_lig = pd.DataFrame(resultado["ligacoes"])

            # ---------- FILTROS ----------
            st.subheader("🔎 Filtros")
            c1, c2, c3, c4, c5 = st.columns(5)
            with c1:
                filtro_saida = st.multiselect(
                    "Linha que originou a ligação",
                    sorted(df_lig["linha_origem"].unique()),
                    placeholder="Todas",
                )
            with c2:
                filtro_destino = st.multiselect(
                    "Linha que recebeu a ligação",
                    sorted(df_lig["numero_destino"].unique()),
                    placeholder="Todas",
                )
            with c3:
                filtro_data = st.multiselect(
                    "Data da ligação",
                    sorted(df_lig["data"].unique()),
                    placeholder="Todas",
                )
            with c4:
                filtro_secao = st.multiselect(
                    "Tipo / Seção",
                    sorted(df_lig["secao"].unique()),
                    placeholder="Todas",
                )
            with c5:
                filtro_tarifa = st.multiselect(
                    "Tarifa",
                    sorted(df_lig["tarifa_tipo"].unique()),
                    placeholder="Todas",
                )

            df_filtrado = df_lig.copy()
            if filtro_saida:
                df_filtrado = df_filtrado[df_filtrado["linha_origem"].isin(filtro_saida)]
            if filtro_destino:
                df_filtrado = df_filtrado[df_filtrado["numero_destino"].isin(filtro_destino)]
            if filtro_data:
                df_filtrado = df_filtrado[df_filtrado["data"].isin(filtro_data)]
            if filtro_secao:
                df_filtrado = df_filtrado[df_filtrado["secao"].isin(filtro_secao)]
            if filtro_tarifa:
                df_filtrado = df_filtrado[df_filtrado["tarifa_tipo"].isin(filtro_tarifa)]

            # ---------- ORDENAÇÃO ----------
            st.subheader("Ordenar por")
            col_ord, col_dir = st.columns(2)
            with col_ord:
                coluna_ord = st.selectbox(
                    "Coluna",
                    ["data", "hora", "duracao", "valor", "linha_origem", "numero_destino"],
                    index=0,
                )
            with col_dir:
                direcao = st.radio("Direção", ["Crescente", "Decrescente"], horizontal=True)
            ascending = direcao == "Crescente"

            df_filtrado = df_filtrado.copy()
            df_filtrado["_duracao_seg"] = df_filtrado["duracao"].apply(
                lambda d: int(d.split("m")[0]) * 60 + int(d.split("m")[1].replace("s", ""))
                if isinstance(d, str) and "m" in d else 0
            )
            chave = "_duracao_seg" if coluna_ord == "duracao" else coluna_ord
            df_filtrado = df_filtrado.sort_values(chave, ascending=ascending)

            # ---------- TABELA ----------
            st.subheader(f"📋 Ligações ({len(df_filtrado)} registros)")
            st.dataframe(
                df_filtrado.drop(columns=["_duracao_seg"]),
                use_container_width=True,
                hide_index=True,
                column_config={"valor": st.column_config.NumberColumn(format="R$ %.2f")},
            )

            # ---------- RESUMO + EXPORT ----------
            with st.expander("📊 Resumo por linha de origem e exportar"):
                resumo = (
                    df_filtrado.groupby("linha_origem")
                    .agg(
                        qtd=("numero_destino", "size"),
                        duracao_total_seg=("_duracao_seg", "sum"),
                        valor_total=("valor", "sum"),
                    )
                    .reset_index()
                )
                st.dataframe(resumo, use_container_width=True, hide_index=True)

                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                    df_filtrado.drop(columns=["_duracao_seg"]).to_excel(
                        writer, index=False, sheet_name="Ligações"
                    )
                    resumo.to_excel(writer, index=False, sheet_name="Resumo")
                st.download_button(
                    "📥 Baixar Excel (filtrado)",
                    data=buffer.getvalue(),
                    file_name="ligacoes_vivo.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )