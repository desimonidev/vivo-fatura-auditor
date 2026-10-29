import streamlit as st
import pandas as pd
import tempfile
import os
import io
from parser import ler_fatura_completa, _diagnosticar_diarias_travel

st.set_page_config(page_title="Auditor Vivo", page_icon="📱", layout="wide")
st.title("📱 Auditor de Faturas Vivo")

if "resultado" not in st.session_state:
    st.session_state.resultado = None
if "arquivo_hash" not in st.session_state:
    st.session_state.arquivo_hash = None

arquivo_pdf = st.file_uploader("Escolha a fatura (PDF)", type=["pdf"])

if arquivo_pdf is not None:
    hash_atual = hash(arquivo_pdf.getvalue())
    if st.session_state.arquivo_hash != hash_atual:
        st.session_state.resultado = None
        st.session_state.arquivo_hash = hash_atual

    if st.button("Processar Fatura", type="primary"):
        with st.spinner("Lendo o PDF..."):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(arquivo_pdf.getvalue())
                caminho_tmp = tmp.name
            try:
                st.session_state.resultado = ler_fatura_completa(caminho_tmp)
            except Exception as e:
                st.error(f"Erro ao processar: {e}")
            finally:
                if os.path.exists(caminho_tmp): os.unlink(caminho_tmp)

resultado = st.session_state.resultado
if resultado is not None:
    aba_fatura, aba_ligacoes, aba_excedentes = st.tabs([
        "📄 Resumo da Fatura", "📞 Análise de Ligações", "⚠️ Análise de Excedentes"
    ])

    # ---------- ABA 1: FATURA ----------
    with aba_fatura:
        valor_conta_total = resultado.get("boleto", {}).get("total_pagar", resultado["soma_mensalidades"])
        tem_parcelamento = resultado.get("tem_parcelamento", False)
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Quantidade de Linhas", resultado["total_linhas"])
        col2.metric("Valor Total Conta (R$)", f"{valor_conta_total:.2f}")

        if tem_parcelamento:
            total_parc = sum(l.get("parcelamento", 0) for l in resultado["linhas"] if isinstance(l.get("parcelamento"), (int, float)))
            col3.metric("Valor Parcelamento (R$)", f"{total_parc:.2f}")

        lista_limpa = []
        for l in resultado["linhas"]:
            val_parc = l.get("parcelamento", 0.0) if tem_parcelamento else None
            parc_num = float(val_parc) if isinstance(val_parc, (int, float)) else None

            lista_limpa.append({
                "Número Vivo": l["numero"],
                "Plano": l["plano"],
                "Mensalidade (R$)": l["mensalidade"],
                "Consumo (GB)": l["consumo_dados_gb"],
                "Pacote Travel (R$)": l.get("pacote_travel_valor"),
                "Nome Pacote": l.get("pacote_travel_nome"),
                "Parcelamento (R$)": parc_num,
                "Parcela": l.get("parcela", "-") if tem_parcelamento else "-",
            })

        df_fatura = pd.DataFrame(lista_limpa)
        # Ordenação natural preservando o traço (ex: 11-91008)
        df_fatura = df_fatura.sort_values(by="Número Vivo")

        st.dataframe(
            df_fatura,
            use_container_width=True, hide_index=True,
            column_config={
                "Mensalidade (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
                "Parcelamento (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
                "Pacote Travel (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
                "Consumo (GB)": st.column_config.NumberColumn(format="%.2f GB"),
            },
        )

        st.divider()
        st.subheader("🧾 Informações da Fatura")
        col_nf, col_boleto = st.columns(2)
        maior_nf, boleto, ciclo = resultado.get("maior_nfcom"), resultado.get("boleto", {}), resultado.get("ciclo_fatura", "-")

        with col_nf:
            st.markdown("**Dados da NFCOM Principal**")
            if maior_nf:
                st.write(f"**NFCOM:** {maior_nf['nfcom']} (Série {maior_nf['serie']})")
                st.write(f"**Data de Emissão:** {maior_nf.get('data_emissao', '-')}")
                st.write(f"**Valor da NF:** R$ {maior_nf['valor_total']:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            else: st.info("Nenhuma NFCOM encontrada no PDF.")

        with col_boleto:
            st.markdown("**Dados do Boleto**")
            if boleto:
                st.write(f"**Vencimento:** {boleto.get('vencimento', '-')}")
                st.write(f"**Mês de Referência:** {boleto.get('mes_referencia', '-')}")
                st.write(f"**Ciclo da Fatura:** {ciclo}")
                st.write(f"**Total a Pagar:** R$ {boleto.get('total_pagar', 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            else: st.info("Dados do boleto não encontrados.")

    # ---------- ABA 2: LIGAÇÕES ----------
    with aba_ligacoes:
        if not resultado["ligacoes"]:
            st.warning("Nenhuma ligação encontrada no PDF.")
        else:
            df_lig = pd.DataFrame(resultado["ligacoes"])
            st.subheader("🔎 Filtros")
            c1, c2, c3, c4, c5 = st.columns(5)
            with c1: filtro_saida = st.multiselect("Linha que originou", sorted(df_lig["linha_origem"].unique()), placeholder="Todas")
            with c2: filtro_destino = st.multiselect("Linha discada", sorted(df_lig["numero_destino"].unique()), placeholder="Todas")
            with c3: filtro_data = st.multiselect("Data", sorted(df_lig["data"].unique()), placeholder="Todas")
            with c4: filtro_secao = st.multiselect("Tipo / Seção", sorted(df_lig["secao"].unique()), placeholder="Todas")
            with c5: filtro_tarifa = st.multiselect("Tarifa", sorted(df_lig["tarifa_tipo"].unique()), placeholder="Todas")

            df_filtrado = df_lig.copy()
            if filtro_saida: df_filtrado = df_filtrado[df_filtrado["linha_origem"].isin(filtro_saida)]
            if filtro_destino: df_filtrado = df_filtrado[df_filtrado["numero_destino"].isin(filtro_destino)]
            if filtro_data: df_filtrado = df_filtrado[df_filtrado["data"].isin(filtro_data)]
            if filtro_secao: df_filtrado = df_filtrado[df_filtrado["secao"].isin(filtro_secao)]
            if filtro_tarifa: df_filtrado = df_filtrado[df_filtrado["tarifa_tipo"].isin(filtro_tarifa)]

            st.subheader("Ordenar por")
            col_ord, col_dir = st.columns(2)
            with col_ord: coluna_ord = st.selectbox("Coluna", ["data", "hora", "duracao", "valor", "linha_origem", "numero_destino"], index=0)
            with col_dir: direcao = st.radio("Direção", ["Crescente", "Decrescente"], horizontal=True)
            
            df_filtrado = df_filtrado.copy()
            df_filtrado["_duracao_seg"] = df_filtrado["duracao"].apply(lambda d: int(d.split("m")[0]) * 60 + int(d.split("m")[1].replace("s", "")) if isinstance(d, str) and "m" in d else 0)
            chave = "_duracao_seg" if coluna_ord == "duracao" else coluna_ord
            df_filtrado = df_filtrado.sort_values(chave, ascending=(direcao == "Crescente"))

            st.subheader(f"📋 Ligações ({len(df_filtrado)} registros)")
            st.dataframe(df_filtrado.drop(columns=["_duracao_seg"]), use_container_width=True, hide_index=True, column_config={"valor": st.column_config.NumberColumn(format="R$ %.2f")})

            with st.expander("📊 Resumo por linha de origem e exportar"):
                resumo = df_filtrado.groupby("linha_origem").agg(qtd=("numero_destino", "size"), duracao_total_seg=("_duracao_seg", "sum"), valor_total=("valor", "sum")).reset_index()
                st.dataframe(resumo, use_container_width=True, hide_index=True)
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                    df_filtrado.drop(columns=["_duracao_seg"]).to_excel(writer, index=False, sheet_name="Ligações")
                    resumo.to_excel(writer, index=False, sheet_name="Resumo")
                st.download_button("📥 Baixar Excel", data=buffer.getvalue(), file_name="ligacoes_vivo.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    # ---------- ABA 3: EXCEDENTES ----------
    with aba_excedentes:
        st.subheader("⚠️ Análise de Excedentes e Serviços Adicionais")
        st.caption("Aqui mostramos tudo o que foi cobrado além da mensalidade base do plano. Pacotes mensais de Vivo Travel são considerados esperados e não aparecem aqui.")
        
        tem_diarias = bool(resultado.get("excedentes_diarias"))
        tem_ligacoes = bool(resultado.get("excedentes_ligacoes"))

        if not tem_diarias and not tem_ligacoes:
            st.success("🎉 Boa notícia! Não foram encontradas cobranças de excedentes, diárias avulsas ou serviços adicionais nesta fatura.")
        else:
            if tem_diarias:
                st.markdown("### ✈️ Diárias de Vivo Travel (Avulsas) - Agrupado por Linha")
                
                agrupamento_diarias = {}
                
                for d in resultado["excedentes_diarias"]:
                    linha = d["linha"]
                    valor = d["valor"]
                    
                    if linha not in agrupamento_diarias:
                        agrupamento_diarias[linha] = {
                            "Linha": linha,
                            "Qtd. Total Dias": 0,
                            "Valor Total (R$)": 0.0,
                            "Detalhamento Região": []
                        }
                    
                    agrupamento_diarias[linha]["Qtd. Total Dias"] += 1
                    agrupamento_diarias[linha]["Valor Total (R$)"] += valor
                    
                    diag = _diagnosticar_diarias_travel(valor)
                    if diag and diag.get("possibilidades"):
                        regiao = diag["possibilidades"][0]
                        if regiao["americas_europa"] > 0:
                            agrupamento_diarias[linha]["Detalhamento Região"].append("Américas/Europa")
                        elif regiao["mundo"] > 0:
                            agrupamento_diarias[linha]["Detalhamento Região"].append("Mundo")
                        else:
                            agrupamento_diarias[linha]["Detalhamento Região"].append("Mista")

                lista_agrupada = []
                for linha, dados in agrupamento_diarias.items():
                    qtd_americas = dados["Detalhamento Região"].count("Américas/Europa")
                    qtd_mundo = dados["Detalhamento Região"].count("Mundo")
                    
                    resumo_regiao = f"{qtd_americas} dia(s) A/E + {qtd_mundo} dia(s) Mundo"
                    
                    lista_agrupada.append({
                        "Linha": dados["Linha"],
                        "Total de Dias": dados["Qtd. Total Dias"],
                        "Resumo das Regiões": resumo_regiao,
                        "Valor Total (R$)": dados["Valor Total (R$)"]
                    })

                df_diarias_agrup = pd.DataFrame(lista_agrupada)
                df_diarias_agrup = df_diarias_agrup.sort_values(by="Linha")

                st.dataframe(
                    df_diarias_agrup, 
                    use_container_width=True, 
                    hide_index=True,
                    column_config={"Valor Total (R$)": st.column_config.NumberColumn(format="R$ %.2f")}
                )
                
                with st.expander("Ver detalhamento dia a dia (bruto)"):
                    df_bruto = pd.DataFrame(resultado["excedentes_diarias"])
                    df_bruto = df_bruto.sort_values(by="linha")
                    st.dataframe(df_bruto, use_container_width=True, hide_index=True)

            if tem_ligacoes:
                st.markdown("### 📞 Ligações Excedentes - Agrupado por Linha")
                
                df_lig_exc = pd.DataFrame(resultado["excedentes_ligacoes"])
                
                df_lig_agrupado = df_lig_exc.groupby("linha").agg(
                    Qtd_Ligacoes=("servico", "count"),
                    Valor_Total=("valor", "sum")
                ).reset_index()
                
                df_lig_agrupado.columns = ["Linha", "Qtd. Ligações", "Valor Total (R$)"]
                df_lig_agrupado = df_lig_agrupado.sort_values(by="Linha")
                
                st.dataframe(
                    df_lig_agrupado, 
                    use_container_width=True, 
                    hide_index=True,
                    column_config={"Valor Total (R$)": st.column_config.NumberColumn(format="R$ %.2f")}
                )
                
                with st.expander("Ver detalhamento das ligações (bruto)"):
                    df_lig_exc = df_lig_exc.sort_values(by="linha")
                    st.dataframe(
                        df_lig_exc, 
                        use_container_width=True, 
                        hide_index=True,
                        column_config={"valor": st.column_config.NumberColumn(format="R$ %.2f")}
                    )