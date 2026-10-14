"""Ranking de relevância dos pacotes Debian no grafo de dependências de execução.

Grafo: aresta A -> B quando A tem B em Depends/Pre-Depends (só a 1ª alternativa de `a | b`).
Métricas: PageRank, dependentes diretos (grau de entrada) e dependentes transitivos.

A coluna `category` vem de classification/categories.csv (curadoria manual), quando existir.

Uso: python -I ranking.py <Packages> <dir_import> <dir_saida> [top_n]
Gera <dir_saida>/ranking_all.csv (todos os pacotes) e <dir_saida>/top<N>_libs.csv
(apenas bibliotecas: Section libs/oldlibs, sem os pacotes *-cross de compilação cruzada).
"""
import csv
import sys
from pathlib import Path

import networkx as nx

sys.path.insert(0, str(Path(__file__).parent))
from deb2neo4j import paragraphs  # noqa: E402

LIB_SECTIONS = {"libs", "oldlibs"}
CATEGORIES = Path(__file__).parent.parent / "classification" / "categories.csv"
COLUMNS = ["rank", "package", "category", "source", "version", "section", "description", "tags", "homepage",
           "pagerank", "direct_dependents", "transitive_dependents"]


def main(packages_path, import_dir, out_dir, top_n=200):
    meta = {}
    for p in paragraphs(packages_path):
        meta.setdefault(p["Package"], p)

    categories = {}
    if CATEGORIES.exists():
        with open(CATEGORIES) as fh:
            categories = {r["package"]: r["category"] for r in csv.DictReader(fh)}

    G = nx.DiGraph()
    with open(Path(import_dir) / "depends_on.csv") as fh:
        for r in csv.DictReader(fh):
            if r["kind"] in ("Depends", "Pre-Depends") and r["alt_index:int"] == "0":
                G.add_edge(r[":START_ID(Package)"], r[":END_ID(Package)"])

    pr = nx.pagerank(G)
    rev = G.reverse(copy=False)
    rows = []
    for n in sorted(G, key=pr.get, reverse=True):
        p = meta.get(n, {})
        rows.append({
            "package": n,
            "category": categories.get(n, ""),
            "source": p.get("Source", n if p else "").split(" ")[0],
            "version": p.get("Version", ""),
            "section": p.get("Section", ""),
            "description": p.get("Description", ""),
            "tags": p.get("Tag", ""),
            "homepage": p.get("Homepage", ""),
            "pagerank": f"{pr[n]:.6f}",
            "direct_dependents": G.in_degree(n),
            "transitive_dependents": len(nx.descendants(rev, n)),
        })

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    def write(path, selected):
        with open(path, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=COLUMNS)
            w.writeheader()
            for i, row in enumerate(selected, 1):
                w.writerow({"rank": i, **row})

    write(out / "ranking_all.csv", rows)
    libs = [r for r in rows if r["section"] in LIB_SECTIONS and not r["package"].endswith("-cross")][:int(top_n)]
    write(out / f"top{top_n}_libs.csv", libs)
    print(f"{len(rows)} pacotes ranqueados; top {len(libs)} libs em {out}/top{top_n}_libs.csv")


if __name__ == "__main__":
    main(*sys.argv[1:5])
