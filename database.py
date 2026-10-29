import json
import re
import sqlite3
import unicodedata

DB_NAME = "faturas.db"


def normalizar_nome_empresa(nome: str) -> str:
    """Converte a razão social em um nome curto para a interface."""
    if not nome:
        return "EMPRESA DESCONHECIDA"

    nome = str(nome).strip().upper()
    nome = unicodedata.normalize("NFKD", nome)
    nome = "".join(
        caractere
        for caractere in nome
        if not unicodedata.combining(caractere)
    )
    nome = re.sub(r"[^A-Z0-9\s]", " ", nome)
    nome = re.sub(r"\s+", " ", nome).strip()

    if not nome:
        return "EMPRESA DESCONHECIDA"

    palavras_excluidas = {
        "DO", "DA", "DE", "DOS", "DAS", "E", "EM", "A", "O", "AS", "OS",
        "BRASIL", "NEGOCIOS", "COMERCIO", "INDUSTRIA", "SERVICO", "SERVICOS",
        "TECNOLOGIA", "TECNOLOGIAS", "EMBALAGEM", "EMBALAGENS",
        "LTDA", "LIMITADA", "SA", "S", "ME", "EPP", "CIA", "COMPANHIA",
    }

    palavras = nome.split()
    return next(
        (
            palavra[:30]
            for palavra in palavras
            if palavra not in palavras_excluidas and len(palavra) > 1
        ),
        palavras[0][:30],
    )


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS faturas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente TEXT NOT NULL,
            mes_referencia TEXT NOT NULL,
            vencimento TEXT NOT NULL,
            valor_total REAL NOT NULL,
            data_processamento TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            dados_json TEXT NOT NULL,
            UNIQUE(cliente, mes_referencia, vencimento)
        )
        """
    )
    conn.commit()
    conn.close()


def corrigir_empresas_existentes():
    """
    Migra os nomes antigos para nomes curtos.

    Se duas linhas se tornarem iguais após a normalização, mantém a primeira
    e remove a duplicata lógica, evitando a violação da constraint UNIQUE.

    Esta função deve ser executada manualmente uma vez, e não dentro de
    buscar_empresas().
    """
    init_db()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, cliente, mes_referencia, vencimento, dados_json
        FROM faturas
        ORDER BY id
        """
    )
    registros = cursor.fetchall()

    atualizados = 0
    removidos = 0

    try:
        for fatura_id, cliente_atual, mes_ref, vencimento, dados_json in registros:
            try:
                dados = json.loads(dados_json)
            except (json.JSONDecodeError, TypeError):
                dados = {}

            razao_social = (
                dados.get("razao_social_completa")
                or dados.get("cliente")
                or cliente_atual
                or "EMPRESA DESCONHECIDA"
            )
            nome_curto = normalizar_nome_empresa(razao_social)
            dados["cliente"] = nome_curto
            dados["razao_social_completa"] = razao_social
            novo_json = json.dumps(dados, ensure_ascii=False)

            cursor.execute(
                """
                SELECT id
                FROM faturas
                WHERE cliente = ?
                  AND mes_referencia = ?
                  AND vencimento = ?
                  AND id <> ?
                LIMIT 1
                """,
                (nome_curto, mes_ref, vencimento, fatura_id),
            )
            conflito = cursor.fetchone()

            if conflito:
                # A linha mais antiga já representa a mesma combinação lógica.
                cursor.execute("DELETE FROM faturas WHERE id = ?", (fatura_id,))
                removidos += 1
            else:
                cursor.execute(
                    """
                    UPDATE faturas
                    SET cliente = ?, dados_json = ?
                    WHERE id = ?
                    """,
                    (nome_curto, novo_json, fatura_id),
                )
                atualizados += 1

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {"atualizados": atualizados, "duplicatas_removidas": removidos}


def salvar_fatura(dados_extraidos: dict) -> bool:
    init_db()

    razao_social = (
        dados_extraidos.get("razao_social_completa")
        or dados_extraidos.get("cliente")
        or "EMPRESA DESCONHECIDA"
    )
    cliente = normalizar_nome_empresa(razao_social)

    dados_para_salvar = dict(dados_extraidos)
    dados_para_salvar["cliente"] = cliente
    dados_para_salvar["razao_social_completa"] = razao_social

    boleto = dados_para_salvar.get("boleto") or {}
    mes_ref = boleto.get("mes_referencia") or "-"
    vencimento = boleto.get("vencimento") or "-"
    valor_total = boleto.get("total_pagar") or 0.0
    dados_json = json.dumps(dados_para_salvar, ensure_ascii=False)

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO faturas
                (cliente, mes_referencia, vencimento, valor_total, dados_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (cliente, mes_ref, vencimento, valor_total, dados_json),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def buscar_empresas():
    """Retorna empresas e quantidade de faturas sem executar migração automática."""
    init_db()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT cliente, COUNT(id) AS qtd
        FROM faturas
        GROUP BY cliente
        ORDER BY cliente COLLATE NOCASE
        """
    )
    resultados = cursor.fetchall()
    conn.close()
    return resultados


def buscar_faturas_empresa(cliente, vencimento_filtro=None):
    init_db()
    cliente = normalizar_nome_empresa(cliente)

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    query = """
        SELECT id, cliente, mes_referencia, vencimento,
               valor_total, data_processamento
        FROM faturas
        WHERE cliente = ?
    """
    params = [cliente]

    if vencimento_filtro:
        query += " AND vencimento LIKE ?"
        params.append(f"%{vencimento_filtro.strip()}%")

    query += """
        ORDER BY
            substr(vencimento, 7, 4) DESC,
            substr(vencimento, 4, 2) DESC,
            substr(vencimento, 1, 2) DESC,
            id DESC
    """

    cursor.execute(query, params)
    resultados = cursor.fetchall()
    conn.close()

    return [
        {
            "id": registro[0],
            "cliente": registro[1],
            "mes_referencia": registro[2],
            "vencimento": registro[3],
            "valor_total": registro[4],
            "data_processamento": registro[5],
        }
        for registro in resultados
    ]


def carregar_dados_fatura(fatura_id: int):
    init_db()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT dados_json FROM faturas WHERE id = ?",
        (fatura_id,),
    )
    resultado = cursor.fetchone()
    conn.close()

    if not resultado:
        return None

    try:
        return json.loads(resultado[0])
    except (json.JSONDecodeError, TypeError):
        return None
