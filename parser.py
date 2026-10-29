"""
parser.py — Auditor de Faturas Vivo
Extrai: linhas SMART, mensalidade, consumo de franquia, Vivo Travel e LIGAÇÕES.
Layout alvo: faturas Vivo Empresas (PDF texto selecionável, extraído via PyMuPDF).
"""

import re
import fitz  # PyMuPDF


# ============================================================
# 1) REGEX — LINHAS / PLANOS / MENSALIDADE
# ============================================================

RE_SMART = re.compile(
    r"(\d{2}-\d{4,5}-\d{4})\s+"                                # número (11-99999-9999)
    r"((?:SMART\s+EMPRESAS\s+[\w\.]+\s+(?:TE|CD|TD))|(?:PLANO\s+BASE\s+INTERNET\s+PJ))\s+"  # plano
    r"(\d{1,3}(?:\.\d{3})*,\d{2})",                             # valor
    re.IGNORECASE,
)

# Cabeçalho da seção de detalhamento por linha
RE_TITULO_NUMERO = re.compile(
    r"VEJA\s+O\s+USO\s+DETALHADO\s+DO\s+VIVO\s+(\d{2}-\d{4,5}-\d{4})",
    re.IGNORECASE,
)


# ============================================================
# 2) REGEX — CONSUMO DE FRANQUIA
# ============================================================

RE_CONSUMO_FRANQUIA = re.compile(
    r"FRANQUIA\s+INTERNET\s+COMPARTILHADA\s+"
    r"(?:\d+,\d+\s*GB|\d+\s*GB|[\d,\.]+\s*TB)?\s*"
    r"(\d+(?:,\d+)?\s*(?:MB|GB|TB)\s*(?:\d+\s*KB)?|[\d,\.]+\s*TB)",
    re.IGNORECASE | re.DOTALL,
)


# ============================================================
# 3) REGEX — VIVO TRAVEL
# ============================================================

RE_TRAVEL_EXATO = re.compile(
    r"(VIVO\s+TRAVEL\s+[\wÀ-ÿ\s]+?)\s+.*?\s+-\s+-\s+(\d{1,3}(?:\.\d{3})*,\d{2})",
    re.IGNORECASE,
)


# ============================================================
# 4) REGEX — LIGAÇÕES (BLOCO MULTI-LINHA DO PYMUPDF)
# ============================================================
#
# O PyMuPDF extrai cada célula numa linha. O bloco real é:
#
#   15/09/26
#   16:30:58
#   DDD 011
#   11-97634-0923
#   (opcional: tarifa, ex: "- VO" | "Normal" | "Reduzida")
#   01m48s
#   0,00
#
# Quando a coluna Tarifa vem vazia, o PyMuPDF simplesmente PULA a linha
# e o próximo token já é a duração. Por isso a tarifa é opcional.

RE_LIGACAO_BLOCO = re.compile(
    r"(?P<data>\d{2}/\d{2}/\d{2})\s*\n\s*"
    r"(?P<hora>\d{2}:\d{2}:\d{2})\s*\n\s*"
    r"(?P<localidade>DDD\s+\d+)\s*\n\s*"
    r"(?P<numero>[\d\-]+)\s*\n\s*"
    r"(?P<tarifa>(?:[-\wÀ-ÿ][^\n]*?))?\s*\n?\s*"                # tarifa opcional
    r"(?P<duracao>\d{2}m\d{2}s)\s*\n\s*"
    r"(?P<valor>\d{1,3}(?:\.\d{3})*,\d{2})",
    re.MULTILINE | re.DOTALL,
)


# ============================================================
# 5) REGEX — SEÇÕES (para classificar cada ligação)
# ============================================================

RE_SECAO = re.compile(
    r"("
    r"Utilização\s+Acima\s+do\s+Contratado"
    r"|Ligações\s+de\s+Longa\s+Distância"
    r"|Ligações\s+Locais[^\n]*"
    r"|NO\s+BRASIL\s*-\s*EM\s+ROAMING"
    r"|Para\s+Celulares\s+Vivo"
    r"|Para\s+Celulares\s+de\s+Outras\s+Operadoras"
    r"|Para\s+Fixo\s+Vivo"
    r"|Para\s+Fixo\s+de\s+Outras\s+Operadoras"
    r"|Para\s+Outros\s+Estados[^\n]*"
    r"|Para\s+Dentro\s+do\s+Estado[^\n]*"
    r"|Para\s+Outros\s+Países"
    r"|OPERADORA\s+\d+[^\n]*"
    r")",
    re.IGNORECASE,
)


# ============================================================
# 6) HELPERS
# ============================================================

def _para_float(s: str) -> float:
    """'1.234,56' -> 1234.56"""
    return float(s.replace(".", "").replace(",", "."))


def _normaliza_telefone(tel: str) -> str:
    """Remove tudo que não é dígito."""
    return re.sub(r"\D", "", tel)


def _converter_para_gb(consumo_str: str) -> float:
    """Converte 'X MB Y KB' / 'X GB' / 'X,Y TB' em GB (float)."""
    if not consumo_str or consumo_str == "-":
        return 0.0
    consumo_str = str(consumo_str).upper()
    total_gb = 0.0
    partes = re.findall(r"(\d+(?:[.,]\d+)?)\s*(TB|GB|MB|KB)", consumo_str)
    for valor_str, unidade in partes:
        try:
            valor = float(valor_str.replace(",", "."))
            if unidade == "TB":
                total_gb += valor * 1024.0
            elif unidade == "GB":
                total_gb += valor
            elif unidade == "MB":
                total_gb += valor / 1024.0
            elif unidade == "KB":
                total_gb += valor / (1024.0 * 1024.0)
        except ValueError:
            pass
    return round(total_gb, 3)


def _secao_em(pos: int, secoes: list[tuple[int, str]]) -> str:
    """Dado um offset no texto, retorna o nome da seção mais recente antes dele."""
    atual = "OUTROS"
    for ini, nome in secoes:
        if ini <= pos:
            atual = nome
        else:
            break
    return atual


# ============================================================
# 7) EXTRAÇÃO DE LIGAÇÕES POR PÁGINA
# ============================================================

def _extrair_ligacoes_pagina(texto_pagina: str, num_linha: str) -> list[dict]:
    ligacoes = []

    # lista de (offset, nome_da_seção) para classificar cada ligação
    secoes = [(m.start(), re.sub(r"\s+", " ", m.group(1)).strip())
              for m in RE_SECAO.finditer(texto_pagina)]

    for m in RE_LIGACAO_BLOCO.finditer(texto_pagina):
        secao = _secao_em(m.start(), secoes)

        # descarta o que for internet (não é ligação)
        if "INTERNET" in secao.upper():
            continue

        tarifa = (m.group("tarifa") or "").strip()
        # limpa casos como "- VO" / "Normal - VO"
        if not tarifa or tarifa in {"-", "--"}:
            tarifa = "-"

        ligacoes.append({
            "linha_origem": num_linha,
            "secao": secao,
            "data": m.group("data"),
            "hora": m.group("hora"),
            "localidade": m.group("localidade").strip(),
            "numero_destino": _normaliza_telefone(m.group("numero")),
            "tarifa_tipo": tarifa,
            "duracao": m.group("duracao"),
            "valor": _para_float(m.group("valor")),
        })

    return ligacoes


# ============================================================
# 8) FUNÇÃO PRINCIPAL
# ============================================================

def ler_fatura_completa(caminho_pdf: str) -> dict:
    """
    Lê a fatura Vivo e devolve:
        {
            "linhas": [...],                # uma por número, com mensalidade/consumo/travel
            "total_linhas": int,
            "soma_mensalidades": float,
            "ligacoes": [...]               # todas as ligações de todas as linhas
        }
    """
    linhas_moveis = []
    travels_por_linha = {}
    consumo_por_linha = {}
    ligacoes = []

    doc = fitz.open(caminho_pdf)
    try:
        for page in doc:
            texto = page.get_text()
            if not texto:
                continue

            # ---------- 1. Linhas SMART + mensalidade ----------
            for m in RE_SMART.finditer(texto):
                linhas_moveis.append({
                    "numero": _normaliza_telefone(m.group(1)),
                    "plano": re.sub(r"\s+", " ", m.group(2)).strip(),
                    "mensalidade": _para_float(m.group(3)),
                })

            # ---------- 2. Consumo de franquia ----------
            if "FRANQUIA INTERNET COMPARTILHADA" in texto.upper():
                texto_limpo = re.sub(r"\s+", " ", texto)
                m_cons = RE_CONSUMO_FRANQUIA.search(texto_limpo)
                m_titulo = RE_TITULO_NUMERO.search(texto) or re.search(
                    r"VIVO\s+(\d{2}-\d{4,5}-\d{4})", texto
                )
                if m_cons and m_titulo:
                    num = _normaliza_telefone(m_titulo.group(1))
                    consumo_por_linha[num] = m_cons.group(1).strip()

            # ---------- 3. Travel + Ligações (só em páginas de detalhe da linha) ----------
            m_titulo = RE_TITULO_NUMERO.search(texto)
            if not m_titulo:
                continue
            num_pagina = _normaliza_telefone(m_titulo.group(1))

            # Vivo Travel
            if "VIVO TRAVEL" in texto.upper():
                m_travel = RE_TRAVEL_EXATO.search(texto)
                if m_travel:
                    nome_t = re.sub(r"\s+", " ", m_travel.group(1)).strip()
                    valor_t = _para_float(m_travel.group(2))
                    if num_pagina in travels_por_linha:
                        travels_por_linha[num_pagina]["valor"] += valor_t
                        travels_por_linha[num_pagina]["nome"] += f" + {nome_t}"
                    else:
                        travels_por_linha[num_pagina] = {"valor": valor_t, "nome": nome_t}

            # Ligações
            ligacoes.extend(_extrair_ligacoes_pagina(texto, num_pagina))
    finally:
        doc.close()

    # ---------- 4. Consolidação das linhas ----------
    vistos = set()
    linhas_unicas = []
    for item in linhas_moveis:
        if item["numero"] not in vistos:
            vistos.add(item["numero"])
            linhas_unicas.append(item)

    tabela_final = []
    soma_total = 0.0
    for l in linhas_unicas:
        num = l["numero"]
        v_t = travels_por_linha.get(num, {"valor": 0.0, "nome": "-"})
        c_gb = _converter_para_gb(consumo_por_linha.get(num, "-"))

        tabela_final.append({
            "numero": num,
            "plano": l["plano"],
            "mensalidade": l["mensalidade"],
            "consumo_dados_gb": c_gb,
            "travel": v_t["valor"] if v_t["valor"] > 0 else "-",
            "pacote_travel": v_t["nome"],
        })
        soma_total += l["mensalidade"]

    tabela_final.sort(key=lambda x: x["numero"])

    # ---------- 5. Ordenação cronológica das ligações ----------
    def _chave_lig(l):
        # converte "dd/mm/aa" + "HH:MM:SS" em string ordenável "yymmddHHMMSS"
        d = l.get("data", "")
        h = l.get("hora", "")
        try:
            dd, mm, aa = d.split("/")
            hh, mi, ss = h.split(":")
            return f"{aa}{mm}{dd}{hh}{mi}{ss}"
        except Exception:
            return ""

    ligacoes.sort(key=_chave_lig)

    return {
        "linhas": tabela_final,
        "total_linhas": len(tabela_final),
        "soma_mensalidades": round(soma_total, 2),
        "ligacoes": ligacoes,
    }