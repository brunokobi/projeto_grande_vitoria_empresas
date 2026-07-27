"""
Checkpoint simples em JSON: guarda o progresso de processos longos
(ex.: quais CNPJs já foram consultados no DataJud/Places), permitindo
retomar depois de uma queda ou rate limit sem repetir trabalho.
"""
import json
from pathlib import Path

import config


def _path_for(nome: str) -> Path:
    return config.CHECKPOINT_DIR / f"{nome}.json"


def carregar(nome: str) -> set:
    p = _path_for(nome)
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def salvar(nome: str, processados: set):
    p = _path_for(nome)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(sorted(processados), f)


def marcar_processado(nome: str, chave: str):
    """Adiciona uma chave ao checkpoint e persiste imediatamente.
    Menos eficiente que batch, mas garante que nada se perde se o
    processo cair no meio de uma chamada de API com rate limit."""
    atuais = carregar(nome)
    atuais.add(chave)
    salvar(nome, atuais)
