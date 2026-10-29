import hashlib
import hmac
import secrets
import sqlite3
from typing import Optional

from database import DB_NAME


ITERATIONS = 260_000


def init_auth_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            usuario TEXT NOT NULL UNIQUE COLLATE NOCASE,
            senha_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            perfil TEXT NOT NULL DEFAULT 'usuario',
            ativo INTEGER NOT NULL DEFAULT 1,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    conn.close()


def _hash_senha(senha: str, salt: Optional[str] = None) -> tuple[str, str]:
    if salt is None:
        salt = secrets.token_hex(16)
    derivada = hashlib.pbkdf2_hmac(
        "sha256",
        senha.encode("utf-8"),
        salt.encode("utf-8"),
        ITERATIONS,
    )
    return derivada.hex(), salt


def quantidade_usuarios() -> int:
    init_auth_db()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM usuarios")
    quantidade = cursor.fetchone()[0]
    conn.close()
    return int(quantidade)


def criar_usuario(nome: str, usuario: str, senha: str, perfil: str = "usuario"):
    init_auth_db()
    nome = nome.strip()
    usuario = usuario.strip().lower()
    perfil = perfil if perfil in {"admin", "usuario"} else "usuario"

    if not nome or not usuario or len(senha) < 6:
        return False, "Preencha nome e usuário e use uma senha com pelo menos 6 caracteres."

    senha_hash, salt = _hash_senha(senha)
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO usuarios (nome, usuario, senha_hash, salt, perfil)
            VALUES (?, ?, ?, ?, ?)
            """,
            (nome, usuario, senha_hash, salt, perfil),
        )
        conn.commit()
        return True, "Usuário criado com sucesso."
    except sqlite3.IntegrityError:
        return False, "Esse nome de usuário já existe."
    finally:
        conn.close()


def autenticar(usuario: str, senha: str):
    init_auth_db()
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, nome, usuario, senha_hash, salt, perfil
        FROM usuarios
        WHERE usuario = ? AND ativo = 1
        """,
        (usuario.strip().lower(),),
    )
    registro = cursor.fetchone()
    conn.close()

    if not registro:
        return None

    senha_hash, _ = _hash_senha(senha, registro["salt"])
    if not hmac.compare_digest(senha_hash, registro["senha_hash"]):
        return None

    return {
        "id": registro["id"],
        "nome": registro["nome"],
        "usuario": registro["usuario"],
        "perfil": registro["perfil"],
    }


def listar_usuarios():
    init_auth_db()
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, nome, usuario, perfil, ativo, criado_em
        FROM usuarios
        ORDER BY nome COLLATE NOCASE
        """
    )
    registros = [dict(registro) for registro in cursor.fetchall()]
    conn.close()
    return registros


def alternar_usuario(usuario_id: int, ativo: bool):
    init_auth_db()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE usuarios SET ativo = ? WHERE id = ?",
        (1 if ativo else 0, usuario_id),
    )
    conn.commit()
    conn.close()
