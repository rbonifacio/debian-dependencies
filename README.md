# Grafo de dependências do Debian

Análise das dependências entre pacotes do Debian para identificar as bibliotecas mais
relevantes, ou seja, aquelas de que mais pacotes dependem, direta ou indiretamente.

O resultado principal é [`results/top100_libs.csv`](results/top100_libs.csv): as 100
bibliotecas mais relevantes da release **trixie (Debian 13)**, seção `main`, arquitetura
`amd64`.

A metodologia completa (snapshot exato do dataset, hashes, etapas do pipeline e
números intermediários) está em [`results/README.md`](results/README.md).

## Fonte dos dados

O Debian publica, por release, dois índices com os metadados de todos os pacotes:

| Arquivo | Conteúdo | Campos usados |
|---|---|---|
| `dists/<suite>/main/binary-<arch>/Packages.xz` | pacotes binários (o que se instala) | `Package`, `Version`, `Source`, `Section`, `Tag`, `Description`, `Depends`, `Pre-Depends`, `Recommends`, `Provides` |
| `dists/<suite>/main/source/Sources.xz` | pacotes fonte (o que se compila) | `Package`, `Version`, `Binary`, `Build-Depends*` |

Na trixie são 68.820 pacotes binários e 37.591 pacotes fonte.

Um pacote fonte gera vários binários. O fonte `curl`, por exemplo, gera `curl`,
`libcurl4t64`, `libcurl3t64-gnutls`, os pacotes `-dev` e a documentação. As dependências
de compilação ficam no fonte (`Build-Depends`), e as de execução em cada binário
(`Depends`).

## Como reproduzir

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

scripts/fetch.sh trixie amd64                    # baixa os índices para data/trixie/
.venv/bin/python -I scripts/deb2neo4j.py \
    data/trixie/Packages data/trixie/Sources import   # gera o grafo em CSV
.venv/bin/python -I scripts/ranking.py \
    data/trixie/Packages import results 100           # gera o ranking
```

`data/`, `import/` e `results/ranking_all.csv` não são versionados, porque podem ser
regenerados com os comandos acima.

## Estrutura

```
scripts/fetch.sh                  download dos índices do Debian
scripts/deb2neo4j.py              parser deb822 -> CSVs do grafo (formato neo4j-admin import)
scripts/ranking.py                cálculo das métricas e geração do ranking
classification/categories.csv     categoria funcional de cada lib (curadoria manual)
results/top100_libs.csv           top 100 bibliotecas
results/ranking_all.csv           ranking de todos os pacotes (não versionado)
```

## Modelo do grafo

`scripts/deb2neo4j.py` gera CSVs prontos para `neo4j-admin database import`, mas que
também servem para qualquer outra ferramenta:

```
(:Package {name, version, section, priority, essential})   pacote binário
(:Package:Virtual {name})                                  pacote virtual (só existe via Provides)
(:Package:Missing {name})                                  referenciado, mas fora de main
(:Source {name, version})                                  pacote fonte

(:Package)-[:DEPENDS_ON {kind, op, version, alt_group, alt_index}]->(:Package)
(:Package)-[:PROVIDES]->(:Package:Virtual)
(:Source)-[:BUILDS]->(:Package)
(:Source)-[:BUILD_DEPENDS {kind, op, version, alt_group, alt_index}]->(:Package)
```

- `kind` é o campo de origem da relação: `Depends`, `Pre-Depends`, `Recommends`,
  `Build-Depends`, `Build-Depends-Arch` ou `Build-Depends-Indep`.
- `op`/`version` guardam a restrição de versão, por exemplo `>=` e `2.38`.
- Alternativas (`a | b`) compartilham o mesmo `alt_group`; `alt_index` dá a ordem, e `0`
  é a alternativa preferida.
- Qualificadores de arquitetura (`[amd64]`) e perfis de build (`<!nocheck>`) são
  descartados.

| Relação | Quantidade |
|---|---|
| `DEPENDS_ON` | 350.996 |
| `PROVIDES` | 68.640 |
| `BUILDS` | 69.427 |
| `BUILD_DEPENDS` | 324.236 |

A maior parte dos ~65 mil pacotes virtuais vem dos pacotes `librust-*-dev`, que declaram
um `Provides` por variante de feature.

## Critério de relevância

`scripts/ranking.py` monta um grafo dirigido com uma aresta `A -> B` sempre que A tem B em
`Depends` ou `Pre-Depends`, considerando só a primeira alternativa de `a | b`. O resultado
são 71.770 nós e 305.206 arestas. Sobre esse grafo ele calcula três métricas:

| Métrica | Significado |
|---|---|
| `pagerank` | PageRank (networkx, damping 0,85). A importância flui de quem depende para a dependência, então uma lib é relevante quando pacotes relevantes dependem dela. **É o critério de ordenação.** |
| `direct_dependents` | número de pacotes que a declaram diretamente em `Depends`/`Pre-Depends` |
| `transitive_dependents` | número de pacotes que dependem dela por qualquer caminho |

Para `top100_libs.csv`, entram apenas os pacotes com `Section` igual a `libs` ou
`oldlibs`. Ficam de fora os pacotes `libc6-*-cross`, que são a libc para compilação
cruzada e só aparecem bem colocados porque o toolchain de cada arquitetura depende do seu.

Exemplos:

| Pacote | Posição entre as libs | Posição entre todos os pacotes | Dependentes diretos | Dependentes transitivos |
|---|---|---|---|---|
| libc6 | 1 | 1 | 22.912 | 50.190 |
| libssl3t64 | 10 | 23 | 917 | 25.872 |
| libxml2 | 30 | 58 | 626 | 13.985 |
| libcurl4t64 | 78 | 185 | 234 | 3.990 |

## Colunas de `top100_libs.csv`

| Coluna | Origem |
|---|---|
| `rank` | posição pelo PageRank entre as libs |
| `package`, `source`, `version`, `section`, `description`, `homepage` | índice `Packages` |
| `tags` | Debtags (campo `Tag`); geralmente vazio ou só `role::shared-lib` |
| `category` | `classification/categories.csv` |
| `pagerank`, `direct_dependents`, `transitive_dependents` | calculados por `ranking.py` |

## Classificação das bibliotecas

O Debian não traz uma classificação funcional útil para as libs:

- `Section: libs` diz apenas que o pacote é uma biblioteca.
- As Debtags quase nunca vão além de `role::shared-lib`, e muitas libs não têm tag nenhuma.
  A transição para `time_t` de 64 bits (sufixo `t64`) deixou pacotes renomeados, como
  `libssl3t64` e `libcurl4t64`, sem as tags que tinham antes.

Por isso, `classification/categories.csv` atribui manualmente uma categoria a cada uma das
200 primeiras libs do ranking (o CSV usa as 100 primeiras; as demais ficam prontas caso
o corte aumente), com base na descrição e no projeto de origem. É uma curadoria inicial e merece
revisão:

| Categoria | Exemplos |
|---|---|
| `runtime-c-cpp` | libc6, libgcc-s1, libstdc++6, libgomp1 |
| `compressao` | zlib1g, libzstd1, liblzma5, libbrotli1 |
| `criptografia-hash` | libssl3t64, libgnutls30t64, libgcrypt20, libcrypt1 |
| `seguranca-autenticacao` | libselinux1, libpam0g, libgssapi-krb5-2, libaudit1 |
| `rede-io` | libcurl4t64, libcurl3t64-gnutls, libqt5network5t64 |
| `parsing-formatos` | libxml2, libexpat1, libyaml-0-2, libpcre2-8-0 |
| `banco-de-dados` | libsqlite3-0, libdb5.3t64, libgdbm6t64 |
| `texto-fontes-i18n` | libicu76, libfreetype6, libharfbuzz0b, libpango-1.0-0 |
| `graficos-imagem` | libcairo2, libpng16-16t64, libjpeg62-turbo, libgl1 |
| `janelas-x11-wayland` | libx11-6, libxcb1, libwayland-client0 |
| `gui-toolkit` | libgtk-3-0t64, libqt6widgets6, libqt5widgets5t64 |
| `utilitarios-base` | libglib2.0-0t64, libqt6core6t64, libffi8, libuuid1 |
| `audio-video` | libasound2t64, libsdl2-2.0-0, libogg0 |
| `calculo-cientifico` | libgmp10, libblas3, liblapack3, libopenmpi40 |
| `sistema-linux` | libsystemd0, libudev1, libdbus-1-3, libmount1 |
| `terminal` | libtinfo6, libncursesw6, libreadline8t64 |
| `linguagem-runtime` | libperl5.40, libruby3.3, libnode115, libtcl8.6 |

Se o top N mudar (outra release, outro N), as libs novas aparecem com `category` vazia e
precisam ser adicionadas ao arquivo.

## Limitações

- Só a primeira alternativa de `a | b` entra no ranking, e dependências em pacotes
  virtuais não são resolvidas para quem os provê.
- Só considera `main`; dependências em `contrib`/`non-free` viram nós `Missing`.
- Só considera dependências de execução; `Recommends` e `Build-Depends` estão no grafo,
  mas não entram no ranking.
- Variantes de uma mesma lib contam separadas, como `libcurl4t64` (OpenSSL) e
  `libcurl3t64-gnutls` (GnuTLS), ou Qt 5 e Qt 6.

## Próximos passos

- Carregar o grafo em um Neo4j (local ou AuraDB) para explorá-lo com Cypher. O plano
  gratuito do AuraDB tem limite de nós e relacionamentos, então cabe apenas o recorte de
  dependências de execução.
- Agregar o ranking por pacote fonte, para unir variantes como as duas libcurl.
