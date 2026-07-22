"""
Orquestrador do pipeline de dados de empresas da Grande Vitória.

Uso:
    python main.py --etapa cnpj
    python main.py --etapa jucees
    python main.py --etapa sancoes
    python main.py --etapa tcees
    python main.py --etapa ibama
    python main.py --etapa datajud --limite 200
    python main.py --etapa geo --limite 200
    python main.py --etapa exportar
    python main.py --etapa tudo

A ordem importa: cnpj precisa rodar primeiro (define o universo de
CNPJs da Grande Vitória que todas as outras etapas usam como filtro).
"""
import argparse

from src import (
    db_utils, cnpj_ingest, jucees_ingest, sanctions_ingest, tcees_ingest,
    ibama_ingest, datajud_client, geo_enrich, contato_enrich, export_dataset,
)


ETAPAS = {
    "cnpj": cnpj_ingest.executar,
    "jucees": jucees_ingest.executar,
    "sancoes": sanctions_ingest.executar,
    "tcees": tcees_ingest.executar,
    "ibama": ibama_ingest.executar,
    "datajud": datajud_client.executar,
    "geo": geo_enrich.executar,
    "contato": contato_enrich.executar,
    "exportar": export_dataset.gerar_dataset_consolidado,
}

ORDEM_TUDO = ["cnpj", "jucees", "sancoes", "tcees", "ibama", "datajud", "geo", "contato", "exportar"]


def main():
    parser = argparse.ArgumentParser(description="Pipeline de dados de empresas da Grande Vitória")
    parser.add_argument(
        "--etapa", choices=list(ETAPAS.keys()) + ["tudo"], required=True,
        help="Qual etapa do pipeline rodar",
    )
    parser.add_argument(
        "--limite", type=int, default=None,
        help="Limite de CNPJs a processar (útil para datajud/geo, que têm rate limit)",
    )
    args = parser.parse_args()

    db_utils.init_db()

    if args.etapa == "tudo":
        for nome in ORDEM_TUDO:
            print(f"\n{'='*60}\nEtapa: {nome}\n{'='*60}")
            if nome in ("datajud", "geo", "contato"):
                ETAPAS[nome](limite_cnpjs=args.limite)
            else:
                ETAPAS[nome]()
    else:
        if args.etapa in ("datajud", "geo", "contato"):
            ETAPAS[args.etapa](limite_cnpjs=args.limite)
        else:
            ETAPAS[args.etapa]()


if __name__ == "__main__":
    main()
