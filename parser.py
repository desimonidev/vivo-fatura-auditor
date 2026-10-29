import re
import fitz  # PyMuPDF

# ============================================================
# REGEX PARA A NOTA FISCAL E TABELAS
# ============================================================

RE_PLANO_VALOR_NF = re.compile(
    r"((?:SMART\s+EMPRESAS\s+[\w\.]+\s+(?:TE|CD|TD))|(?:PLANO\s+BASE\s+INTERNET\s+PJ))"
    r".*?(\d{1,3}(?:\.\d{3})*,\d{2})",
    re.IGNORECASE | re.DOTALL
)

RE_SMART_TABELA = re.compile(
    r"(\d{2}-\d{4,5}-\d{4})\s+"
    r"((?:SMART\s+EMPRESAS\s+[\w\.]+\s+(?:TE|CD|TD))|(?:PLANO\s+BASE\s+INTERNET\s+PJ))\s+"
    r"(\d{1,3}(?:\.\d{3})*,\d{2})",
    re.IGNORECASE,
)

RE_TITULO_NUMERO = re.compile(
    r"VEJA\s+O\s+USO\s+DETALHADO\s+DO\s+VIVO\s+(\d{2}-\d{4,5}-\d{4})",
    re.IGNORECASE,
)

# REGEX DO CLIENTE
RE_CLIENTE = re.compile(
    r"^\s*NOME\s*:\s*(?!DO\s+CLIENTE\b)([^\n]+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)

RE_NFCOM = re.compile(r"N[ºo°]\s*NFCOM\s*(\d+)\s*-\s*S[ÉE]RIE\s*(\d+)(?:/DATA DE EMISSÃO:?\s*(\d{2}/\d{2}/\d{4}))?", re.IGNORECASE)
RE_VENCIMENTO = re.compile(r"Vencimento\s*(\d{2}/\d{2}/\d{4})", re.IGNORECASE)
RE_TOTAL_PAGAR = re.compile(r"Total\s*a\s*Pagar\s*-\s*R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})", re.IGNORECASE)
RE_MES_REF = re.compile(r"M[ÊE]S\s*DE\s*REFER[ÊE]NCIA:?\s*(\d{2}/\d{4})", re.IGNORECASE)
RE_CICLO = re.compile(r"Per[íi]odo:?\s*(\d{2}/\d{2}/\d{4})\s*a\s*(\d{2}/\d{2}/\d{4})", re.IGNORECASE)

RE_CONSUMO_FRANQUIA = re.compile(
    r"FRANQUIA\s+INTERNET\s+COMPARTILHADA\s+"
    r"(?:\d+,\d+\s*GB|\d+\s*GB|[\d,\.]+\s*TB)?\s*"
    r"(\d+(?:,\d+)?\s*(?:MB|GB|TB)\s*(?:\d+\s*KB)?|[\d,\.]+\s*TB)",
    re.IGNORECASE | re.DOTALL,
)

RE_TRAVEL_EXATO = re.compile(
    r"(VIVO\s+TRAVEL\s+[\wÀ-ÿ\s]+?)\s+.*?\s+-\s+-\s+(\d{1,3}(?:\.\d{3})*,\d{2})",
    re.IGNORECASE,
)

RE_PARCELAMENTO = re.compile(
    r"Parcelamento\s+de\s+Aparelho\s*/\s*Acess[óo]rio\s+(\d{2}-\d{4,5}-\d{4})"
    r".*?(\d{1,2}/\d{1,2})\s+(\d{1,3}(?:\.\d{3})*,\d{2})",
    re.IGNORECASE | re.DOTALL,
)

RE_LIGACAO_BLOCO = re.compile(
    r"(?P<data>\d{2}/\d{2}/\d{2})\s*\n\s*"
    r"(?P<hora>\d{2}:\d{2}:\d{2})\s*\n\s*"
    r"(?P<localidade>DDD\s+\d+)\s*\n\s*"
    r"(?P<numero>[\d\-]+)\s*\n\s*"
    r"(?P<tarifa>(?:[-\wÀ-ÿ][^\n]*?))?\s*\n?\s*"
    r"(?P<duracao>\d{2}m\d{2}s)\s*\n\s*"
    r"(?P<valor>\d{1,3}(?:\.\d{3})*,\d{2})",
    re.MULTILINE | re.DOTALL,
)

RE_SECAO = re.compile(
    r"("
    r"Utilização\s+Acima\s+do\s+Contratado|Ligações\s+de\s+Longa\s+Distância|Ligações\s+Locais[^\n]*|"
    r"NO\s+BRASIL\s*-\s*EM\s+ROAMING|Para\s+Celulares\s+Vivo|Para\s+Celulares\s+de\s+Outras\s+Operadoras|"
    r"Para\s+Fixo\s+Vivo|Para\s+Fixo\s+de\s+Outras\s+Operadoras|Para\s+Outros\s+Estados[^\n]*|"
    r"Para\s+Dentro\s+do\s+Estado[^\n]*|Para\s+Outros\s+Países|OPERADORA\s+\d+[^\n]*"
    r")",
    re.IGNORECASE,
)

RE_DIARIA_EXCEDENTE = re.compile(
    r"(\d{2}/\d{2}/\d{2})\s+-\s+DI[ÁA]RIA\s+VIVO\s+TRAVEL\s+(\d+)\s+dia(?:s)?\s+(\d{1,3}(?:\.\d{3})*,\d{2})",
    re.IGNORECASE
)

# PREÇOS: A/E = 39.99 e Mundo = 59.99
PRECO_DIARIA_AMERICAS_EUROPA = 39.99 
PRECO_DIARIA_MUNDO = 59.99 

# ============================================================
# HELPERS
# ============================================================

def _para_float(s: str) -> float:
    return float(s.replace(".", "").replace(",", "."))

def _normaliza_telefone(tel: str) -> str:
    return re.sub(r"\D", "", tel)

def _converter_para_gb(consumo_str: str) -> float:
    if not consumo_str or consumo_str == "-": return 0.0
    consumo_str = str(consumo_str).upper()
    total_gb = 0.0
    partes = re.findall(r"(\d+(?:[.,]\d+)?)\s*(TB|GB|MB|KB)", consumo_str)
    for valor_str, unidade in partes:
        try:
            valor = float(valor_str.replace(",", "."))
            if unidade == "TB": total_gb += valor * 1024.0
            elif unidade == "GB": total_gb += valor
            elif unidade == "MB": total_gb += valor / 1024.0
            elif unidade == "KB": total_gb += valor / (1024.0 * 1024.0)
        except ValueError: pass
    return round(total_gb, 3)

def _limpar_razao_social(nome_completo: str) -> str:
    """
    Transforma 'ATECH - NEGOCIOS EM TECNOLOGIAS SA' em 'ATECH'.
    Transforma 'APTAR DO BRASIL EMBALAGENS LTDA' em 'APTAR'.
    Ignora preposições e palavras genéricas para pegar a raiz real.
    """
    if not nome_completo:
        return "CLIENTE DESCONHECIDO"
    
    # Limpa pontuações e transforma em maiúsculas
    nome_limpo = re.sub(r"[^\w\s]", " ", nome_completo).upper()
    palavras = nome_limpo.split()
    
    if not palavras:
        return "CLIENTE DESCONHECIDO"

    # Lista de preposições e palavras genéricas que não devem ser a raiz
    stop_words = {
        "DO", "DA", "DE", "DOS", "DAS", "E", "EM", "A", "O", "AS", "OS", 
        "NEGOCIOS", "NEGOCIOS", "COMERCIO", "INDUSTRIA", "SERVICOS", "TECNOLOGIA", 
        "TECNOLOGIAS", "EMBALAGENS", "BRASIL", "LTDA", "SA", "S/A", "ME", "EPP"
    }
    
    # Encontra a primeira palavra que não seja stop word
    palavra_base = next((p for p in palavras if p not in stop_words), palavras[0])
    
    # Retorna a palavra base, limitada a 20 caracteres
    return palavra_base[:20]

def _nome_empresa_valido(nome: str) -> bool:
    if not nome:
        return False

    nome_normalizado = re.sub(r"\s+", " ", nome).strip().upper()

    nomes_invalidos = {
        "CLIENTE",
        "DO CLIENTE",
        "EMPRESA",
        "EMPRESA DESCONHECIDA",
        "CLIENTE DESCONHECIDO",
    }

    return (
        nome_normalizado not in nomes_invalidos
        and len(nome_normalizado) >= 3
    )


def _secao_em(pos: int, secoes: list[tuple[int, str]]) -> str:
    atual = "OUTROS"
    for ini, nome in secoes:
        if ini <= pos: atual = nome
        else: break
    return atual

def _extrair_ligacoes_pagina(texto_pagina: str, num_linha: str) -> list[dict]:
    ligacoes = []
    secoes = [(m.start(), re.sub(r"\s+", " ", m.group(1)).strip()) for m in RE_SECAO.finditer(texto_pagina)]
    for m in RE_LIGACAO_BLOCO.finditer(texto_pagina):
        secao = _secao_em(m.start(), secoes)
        if "INTERNET" in secao.upper(): continue
        tarifa = (m.group("tarifa") or "").strip()
        if not tarifa or tarifa in {"-", "--"}: tarifa = "-"
        ligacoes.append({
            "linha_origem": num_linha, "secao": secao, "data": m.group("data"),
            "hora": m.group("hora"), "localidade": m.group("localidade").strip(),
            "numero_destino": _normaliza_telefone(m.group("numero")),
            "tarifa_tipo": tarifa, "duracao": m.group("duracao"),
            "valor": _para_float(m.group("valor")),
        })
    return ligacoes

def _diagnosticar_diarias_travel(valor_total: float) -> dict | None:
    if not valor_total or valor_total <= 0: return None
    A, M, TOL = PRECO_DIARIA_AMERICAS_EUROPA, PRECO_DIARIA_MUNDO, 0.05
    combinacoes = []
    for qtd_mundo in range(0, 31):
        for qtd_americas in range(0, 31):
            if qtd_mundo == 0 and qtd_americas == 0: continue
            total = qtd_mundo * M + qtd_americas * A
            if abs(total - valor_total) <= TOL:
                combinacoes.append({"americas_europa": qtd_americas, "mundo": qtd_mundo, "total_calculado": round(total, 2)})
    combinacoes.sort(key=lambda c: (c["americas_europa"] + c["mundo"], c["mundo"]))
    if not combinacoes:
        return {"valor_total": round(valor_total, 2), "possibilidades": [], "status": "Valor não bate."}
    melhor = combinacoes[0]
    regiao = "Américas/Europa" if melhor["mundo"] == 0 else ("Mundo" if melhor["americas_europa"] == 0 else "Mista")
    return {
        "valor_total": round(valor_total, 2), "possibilidades": combinacoes,
        "regiao_provavel": regiao,
        "resumo": f"{melhor['americas_europa']} dia(s) A/E + {melhor['mundo']} dia(s) Mundo"
    }

# ============================================================
# FUNÇÃO PRINCIPAL
# ============================================================

def ler_fatura_completa(caminho_pdf: str) -> dict:
    linhas_por_numero: dict[str, dict] = {}
    consumo_por_linha: dict[str, str] = {}
    parcelamentos_por_linha: dict[str, dict] = {}
    ligacoes: list[dict] = []
    
    planos_nf = []
    numeros_encontrados = set()
    notas_fiscais = []
    boleto_info = {}
    ciclo_fatura = "-"
    
    diarias_avulsas: list[dict] = []
    pacotes_travel_mensal: dict[str, dict] = {}
    
    razao_social_bruta = "CLIENTE DESCONHECIDO"

    doc = fitz.open(caminho_pdf)
    try:
        for page in doc:
            texto = page.get_text()
            if not texto: continue

            # --- Extrair Nome do Cliente ---
            if razao_social_bruta == "CLIENTE DESCONHECIDO":
                m_cliente = RE_CLIENTE.search(texto)

                if m_cliente:
                    nome_encontrado = m_cliente.group(1).strip()

                    if _nome_empresa_valido(nome_encontrado):
                        razao_social_bruta = nome_encontrado

            if "Total a Pagar" in texto or "NFCOM" in texto:
                m_venc = RE_VENCIMENTO.search(texto)
                m_total = RE_TOTAL_PAGAR.search(texto)
                m_ref = RE_MES_REF.search(texto)
                m_ciclo = RE_CICLO.search(texto)
                if m_ciclo and ciclo_fatura == "-": ciclo_fatura = f"{m_ciclo.group(1)} a {m_ciclo.group(2)}"
                
                if m_venc and m_total and not boleto_info:
                    boleto_info = {"vencimento": m_venc.group(1), "total_pagar": _para_float(m_total.group(1)), "mes_referencia": m_ref.group(1) if m_ref else "-"}
                
                m_nfcom = RE_NFCOM.search(texto)
                if m_nfcom and not notas_fiscais:
                    valor_nf = boleto_info.get("total_pagar", 0.0) 
                    
                    m_valor_nf = re.search(r"VALOR\s+TOTAL\s+NF\s*\n?\s*(\d{1,3}(?:\.\d{3})*,\d{2})", texto, re.IGNORECASE)
                    if m_valor_nf:
                        valor_nf = _para_float(m_valor_nf.group(1))

                    notas_fiscais.append({
                        "nfcom": m_nfcom.group(1), 
                        "serie": m_nfcom.group(2), 
                        "data_emissao": m_nfcom.group(3) if m_nfcom.group(3) else "-",
                        "valor_total": valor_nf, 
                        "pagina": page.number + 1
                    })

            m_titulo = RE_TITULO_NUMERO.search(texto)
            num_pagina = m_titulo.group(1) if m_titulo else None
            if num_pagina: numeros_encontrados.add(num_pagina)

            for m in RE_SMART_TABELA.finditer(texto):
                linhas_por_numero[m.group(1)] = {"plano": re.sub(r"\s+", " ", m.group(2)).strip(), "mensalidade": _para_float(m.group(3)), "fonte": "Tabela"}

            if "ITENS DA FATURA" in texto or "NOTA FISCAL" in texto.upper() or "Nº NFCOM" in texto:
                for m in RE_PLANO_VALOR_NF.finditer(texto):
                    planos_nf.append({"plano": re.sub(r"\s+", " ", m.group(1)).strip(), "valor": _para_float(m.group(2))})

            if "FRANQUIA INTERNET COMPARTILHADA" in texto.upper():
                m_cons = RE_CONSUMO_FRANQUIA.search(re.sub(r"\s+", " ", texto))
                if m_cons and num_pagina: consumo_por_linha[num_pagina] = m_cons.group(1).strip()

            for m in RE_PARCELAMENTO.finditer(texto):
                parcelamentos_por_linha[m.group(1)] = {"valor": _para_float(m.group(3)), "parcela": m.group(2)}

            if num_pagina:
                m_pacote = RE_TRAVEL_EXATO.search(texto)
                if m_pacote:
                    pacotes_travel_mensal[num_pagina] = {
                        "nome": re.sub(r"\s+", " ", m_pacote.group(1)).strip(),
                        "valor": _para_float(m_pacote.group(2))
                    }

                for m_diaria in RE_DIARIA_EXCEDENTE.finditer(texto):
                    v_diaria = _para_float(m_diaria.group(3))
                    if v_diaria > 0:
                        diarias_avulsas.append({
                            "linha": num_pagina,
                            "data": m_diaria.group(1),
                            "quantidade": f"{m_diaria.group(2)} dia(s)",
                            "valor": v_diaria
                        })

                ligacoes.extend(_extrair_ligacoes_pagina(texto, num_pagina))
    finally:
        doc.close()

    if not linhas_por_numero and planos_nf and len(numeros_encontrados) == 1:
        unico_num = list(numeros_encontrados)[0]
        for p in planos_nf:
            if "SMART" in p["plano"].upper(): linhas_por_numero[unico_num] = {"plano": p["plano"], "mensalidade": p["valor"], "fonte": "NF"}; break
        
    maior_nfcom = max(notas_fiscais, key=lambda nf: nf["valor_total"]) if notas_fiscais else None
    tem_parcelamento = len(parcelamentos_por_linha) > 0
    tabela_final = []
    soma_total = 0.0

    for num, dados in sorted(linhas_por_numero.items()):
        c_gb = _converter_para_gb(consumo_por_linha.get(num, "-"))
        if "SERVICO" in dados["plano"].upper() and planos_nf:
            for p in planos_nf:
                if "SMART" in p["plano"].upper():
                    dados["plano"], dados["mensalidade"] = p["plano"], p["valor"]; break

        pacote = pacotes_travel_mensal.get(num, {"nome": "-", "valor": None})

        row = {
            "numero": num, "plano": dados["plano"], "mensalidade": dados["mensalidade"], "consumo_dados_gb": c_gb,
            "pacote_travel_nome": pacote["nome"], "pacote_travel_valor": pacote["valor"]
        }
        if tem_parcelamento:
            p = parcelamentos_por_linha.get(num)
            row["parcelamento"], row["parcela"] = (p["valor"] if p else 0.0), (p["parcela"] if p else "-")
        tabela_final.append(row)
        soma_total += dados["mensalidade"]

    ligacoes.sort(key=lambda x: f"{x.get('data','')} {x.get('hora','')}")
    
    ligacoes_pagas = []
    for l in ligacoes:
        if l["valor"] > 0:
            ligacoes_pagas.append({
                "linha": l["linha_origem"],
                "servico": f"Ligação ({l['duracao']})",
                "data": l["data"],
                "detalhe": l["numero_destino"],
                "valor": l["valor"]
            })

    # APLICA A NOVA FUNÇÃO DE LIMPEZA AQUI
    cliente_minimizado = _limpar_razao_social(razao_social_bruta)

    return {
        "cliente": cliente_minimizado,
        "razao_social_completa": razao_social_bruta,
        "linhas": tabela_final, "total_linhas": len(tabela_final), "soma_mensalidades": round(soma_total, 2),
        "tem_parcelamento": tem_parcelamento, "ligacoes": ligacoes, 
        "excedentes_ligacoes": ligacoes_pagas, "excedentes_diarias": diarias_avulsas,
        "notas_fiscais": notas_fiscais, "maior_nfcom": maior_nfcom, "boleto": boleto_info, "ciclo_fatura": ciclo_fatura
    }