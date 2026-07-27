"""
Validação das URLs de arquivo coladas manualmente em config.py (ou via
variável de ambiente). Evita gastar tempo baixando um HTML de página por
engano quando o link colado não é o arquivo final.
"""
import config


class UrlInvalidaError(Exception):
    pass


def validar_url_arquivo(url: str, nome_fonte: str):
    """
    Levanta erro claro se a URL:
      - ainda é o placeholder padrão (usuário não colou nada)
      - não termina com uma extensão de arquivo reconhecida
    """
    if not url or url.startswith("COLE_AQUI"):
        raise UrlInvalidaError(
            f"[{nome_fonte}] Nenhuma URL de arquivo configurada. "
            f"Abra a página do dataset no navegador, copie a URL final do "
            f"arquivo de exportação e defina a variável de ambiente "
            f"correspondente (veja o comentário em config.py)."
        )
    if not url.lower().endswith(config.EXTENSOES_ARQUIVO_VALIDAS):
        raise UrlInvalidaError(
            f"[{nome_fonte}] A URL configurada não parece apontar para um "
            f"arquivo ({url}). Confirme que é o link direto do CSV/ZIP, "
            f"não a página do dataset."
        )
