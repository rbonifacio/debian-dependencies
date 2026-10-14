"""Converte os índices Packages/Sources do Debian em CSVs para `neo4j-admin database import`.

Modelo:
  (:Package {name, version, section, priority, essential})   pacote binário
  (:Package:Virtual {name})                                  pacote virtual (só existe via Provides)
  (:Package:Missing {name})                                  referenciado, mas fora de main
  (:Source {name, version})                                  pacote fonte

  (:Package)-[:DEPENDS_ON {kind, op, version, alt_group, alt_index}]->(:Package)
  (:Package)-[:PROVIDES]->(:Package:Virtual)
  (:Source)-[:BUILDS]->(:Package)
  (:Source)-[:BUILD_DEPENDS {kind, op, version, alt_group, alt_index}]->(:Package)

Uso: python3 -I deb2neo4j.py <Packages> <Sources> <dir_saida>
"""
import csv
import re
import sys
from pathlib import Path

RUNTIME_FIELDS = ["Pre-Depends", "Depends", "Recommends"]
BUILD_FIELDS = ["Build-Depends", "Build-Depends-Arch", "Build-Depends-Indep"]

DEP_RE = re.compile(
    r"^\s*(?P<name>[a-z0-9][a-z0-9+.\-]*)(?::[a-z0-9\-]+)?"
    r"\s*(?:\(\s*(?P<op><<|<=|=|>=|>>|<|>)\s*(?P<ver>[^)\s]+)\s*\))?"
)


def paragraphs(path):
    """Lê um arquivo deb822 e devolve um dict por parágrafo."""
    fields, key = {}, None
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                if fields:
                    yield fields
                fields, key = {}, None
            elif line[0] in " \t":
                if key:
                    fields[key] += " " + line.strip()
            else:
                key, _, value = line.partition(":")
                fields[key] = value.strip()
    if fields:
        yield fields


def parse_relations(value):
    """'a (>= 1) | b, c [amd64] <!nocheck>' -> [(group, idx, name, op, ver), ...]"""
    out = []
    for group, clause in enumerate(value.split(",")):
        for idx, alt in enumerate(clause.split("|")):
            m = DEP_RE.match(alt)
            if m:
                out.append((group, idx, m["name"], m["op"] or "", m["ver"] or ""))
    return out


def main(packages_path, sources_path, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    packages = {}
    for p in paragraphs(packages_path):
        packages.setdefault(p["Package"], p)  # mantém a primeira versão vista

    referenced, provided = set(), set()
    depends, provides = [], []
    for name, p in packages.items():
        for field in RUNTIME_FIELDS:
            if field in p:
                for group, idx, dep, op, ver in parse_relations(p[field]):
                    depends.append((name, dep, field, op, ver, group, idx))
                    referenced.add(dep)
        if "Provides" in p:
            for _, _, virt, _, _ in parse_relations(p["Provides"]):
                provides.append((name, virt))
                provided.add(virt)

    sources = {}
    for s in paragraphs(sources_path):
        sources.setdefault(s["Package"], s)

    builds, build_deps = [], []
    for name, s in sources.items():
        for b in (x.strip() for x in s.get("Binary", "").split(",")):
            if b in packages:
                builds.append((name, b))
        for field in BUILD_FIELDS:
            if field in s:
                for group, idx, dep, op, ver in parse_relations(s[field]):
                    build_deps.append((name, dep, field, op, ver, group, idx))
                    referenced.add(dep)

    virtual = (provided | referenced) - packages.keys()
    missing = {v for v in virtual if v not in provided}
    virtual -= missing

    with open(out / "packages.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["name:ID(Package)", "version", "section", "priority", "essential:boolean", ":LABEL"])
        for name, p in packages.items():
            w.writerow([name, p.get("Version", ""), p.get("Section", ""), p.get("Priority", ""),
                        p.get("Essential") == "yes", "Package"])
        for name in sorted(virtual):
            w.writerow([name, "", "", "", False, "Package;Virtual"])
        for name in sorted(missing):
            w.writerow([name, "", "", "", False, "Package;Missing"])

    with open(out / "sources.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["name:ID(Source)", "version", ":LABEL"])
        for name, s in sources.items():
            w.writerow([name, s.get("Version", ""), "Source"])

    rel_header = ["kind", "op", "version", "alt_group:int", "alt_index:int"]
    with open(out / "depends_on.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow([":START_ID(Package)", ":END_ID(Package)", *rel_header, ":TYPE"])
        w.writerows([*row, "DEPENDS_ON"] for row in depends)

    with open(out / "provides.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow([":START_ID(Package)", ":END_ID(Package)", ":TYPE"])
        w.writerows([*row, "PROVIDES"] for row in provides)

    with open(out / "builds.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow([":START_ID(Source)", ":END_ID(Package)", ":TYPE"])
        w.writerows([*row, "BUILDS"] for row in builds)

    with open(out / "build_depends.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow([":START_ID(Source)", ":END_ID(Package)", *rel_header, ":TYPE"])
        w.writerows([*row, "BUILD_DEPENDS"] for row in build_deps)

    print(f"pacotes binários: {len(packages)}  virtuais: {len(virtual)}  ausentes: {len(missing)}")
    print(f"fontes: {len(sources)}")
    print(f"DEPENDS_ON: {len(depends)}  PROVIDES: {len(provides)}  "
          f"BUILDS: {len(builds)}  BUILD_DEPENDS: {len(build_deps)}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
