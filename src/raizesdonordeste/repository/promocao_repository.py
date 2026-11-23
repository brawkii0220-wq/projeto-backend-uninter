from __future__ import annotations

from raizesdonordeste.util.tempo import dia_da_semana_local, para_iso


def buscar_campanha(conn, campanha_id: int):
    return conn.execute("SELECT * FROM campanhas WHERE id=?", (campanha_id,)).fetchone()


def buscar_cupom(conn, cupom_id: int):
    return conn.execute("SELECT * FROM cupons WHERE id=?", (cupom_id,)).fetchone()


def buscar_cupom_por_codigo(conn, codigo: str):
    return conn.execute("SELECT * FROM cupons WHERE codigo=?", (codigo,)).fetchone()


def campanha_vigente(conn, unidade_id: int, produto_id: int, momento):
    """Campanha ativa para o produto/unidade no instante, respeitando o dia da semana."""
    agora = para_iso(momento)
    candidatas = conn.execute(
        "SELECT * FROM campanhas WHERE ativa=1 AND produto_id=? AND (unidade_id IS NULL OR unidade_id=?)"
        " AND data_inicio<=? AND data_fim>=?", (produto_id, unidade_id, agora, agora)).fetchall()
    hoje = str(dia_da_semana_local(momento))
    validas = [c for c in candidatas if not c["dias_semana"] or hoje in c["dias_semana"].split(",")]
    return max(validas, key=lambda c: c["percentual_desconto"], default=None)


def campanhas_sobrepostas(conn, produto_id: int, unidade_id, inicio: str, fim: str,
                          dias: set[str], excluir_id: int | None = None):
    """Campanhas ativas do mesmo produto cujo período, escopo (unidade) e dias da semana se cruzam."""
    linhas = conn.execute(
        "SELECT * FROM campanhas WHERE ativa=1 AND produto_id=? AND data_inicio<=? AND data_fim>=?"
        " AND id<>COALESCE(?, -1)", (produto_id, fim, inicio, excluir_id)).fetchall()
    conflitos = []
    for c in linhas:
        mesmo_escopo = unidade_id is None or c["unidade_id"] is None or c["unidade_id"] == unidade_id
        dias_c = set(c["dias_semana"].split(",")) if c["dias_semana"] else set()
        dias_cruzam = not dias or not dias_c or bool(dias & dias_c)
        if mesmo_escopo and dias_cruzam:
            conflitos.append(c)
    return conflitos
