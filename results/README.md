# Como foi gerada a lista das 100 libs mais relevantes

Este documento descreve a origem e a geração de [`top100_libs.csv`](top100_libs.csv): o
dataset de entrada, cada script do pipeline, os filtros aplicados e os números
intermediários. Para uma visão geral do projeto, veja o [README principal](../README.md).

## 1. Dataset inicial

A lista foi gerada a partir dos dois índices oficiais do Debian para a release
**trixie**, na seção `main`, arquitetura `amd64`:

| Índice | URL | Conteúdo |
|---|---|---|
| Binários | <https://deb.debian.org/debian/dists/trixie/main/binary-amd64/Packages.xz> | um parágrafo por pacote binário, com `Depends`, `Pre-Depends`, `Section`, `Tag`, `Description` e outros campos |
| Fontes | <https://deb.debian.org/debian/dists/trixie/main/source/Sources.xz> | um parágrafo por pacote fonte, com `Binary` (os binários que ele gera) e `Build-Depends*` |

Identificação exata do snapshot usado:

| Item | Valor |
|---|---|
| Release | Debian 13.7 (`Codename: trixie`, `Suite: stable`) |
| Data do arquivo `Release` | 2026-09-12 07:55:41 UTC |
| Data do download | 2026-10-14 |
| SHA-256 de `Packages.xz` | `7778d3e3f303b7ddb8ce0fe7c8d57473a076c6bf2e8f241f75421d2396352498` |
| SHA-256 de `Sources.xz` | `6002f81f463a2d976d84b34170367cc16da2d60bd0ba9ab9d868d6e1c1a935d9` |
| Pacotes binários (nomes únicos) | 68.820 |
| Pacotes fonte (nomes únicos) | 37.591 |

Os dois hashes conferem com os listados no arquivo
[`Release`](https://deb.debian.org/debian/dists/trixie/Release) do Debian 13.7.

A URL `dists/trixie` sempre aponta para a versão mais recente da release. Em um novo
ponto de versão (13.8 e seguintes), ela passa a servir índices diferentes. Para reproduzir
exatamente este snapshot, baixe os mesmos arquivos de
[snapshot.debian.org](https://snapshot.debian.org/) a partir de uma data posterior a
2026-09-12 e anterior à 13.8, e confira os hashes acima.

### Binários e fontes

Os dois índices descrevem coisas diferentes:

- O **pacote fonte** é o que se compila. O fonte `curl`, por exemplo, gera os binários
  `curl`, `libcurl4t64`, `libcurl3t64-gnutls`, `libcurl4-openssl-dev`,
  `libcurl4-gnutls-dev` e `libcurl4-doc`. Suas dependências de compilação ficam em
  `Build-Depends`.
- O **pacote binário** é o que se instala. Suas dependências de execução ficam em
  `Depends` e `Pre-Depends`.

O ranking usa as dependências de execução dos **binários**. Os fontes entram no grafo
(relações `BUILDS` e `BUILD_DEPENDS`) e preenchem a coluna `source` do CSV, mas não
influenciam a ordenação.

## 2. Pipeline

```
deb.debian.org ──fetch.sh──▶ data/trixie/{Packages,Sources}
                                   │
                              deb2neo4j.py
                                   ▼
                    import/*.csv  (grafo completo)
                                   │
                              ranking.py  ◀── classification/categories.csv
                                   ▼
          results/ranking_all.csv  +  results/top100_libs.csv
```

| Etapa | Script | Entrada | Saída |
|---|---|---|---|
| 1. Download | [`scripts/fetch.sh`](../scripts/fetch.sh) | mirror do Debian | `data/trixie/Packages`, `data/trixie/Sources` |
| 2. Construção do grafo | [`scripts/deb2neo4j.py`](../scripts/deb2neo4j.py) | `Packages`, `Sources` | `import/packages.csv`, `sources.csv`, `depends_on.csv`, `provides.csv`, `builds.csv`, `build_depends.csv` |
| 3. Ranking | [`scripts/ranking.py`](../scripts/ranking.py) | `Packages`, `import/depends_on.csv`, `classification/categories.csv` | `results/ranking_all.csv`, `results/top100_libs.csv` |

### Etapa 1: download (`fetch.sh`)

Baixa `Packages.xz` e `Sources.xz` da suite e da arquitetura informadas (padrão: `trixie`
e `amd64`) e descompacta os dois em `data/<suite>/`.

### Etapa 2: construção do grafo (`deb2neo4j.py`)

1. Lê os dois índices no formato deb822, em que os parágrafos são separados por linha em
   branco e as linhas de continuação começam com espaço.
2. Para cada nome de pacote, mantém o primeiro parágrafo encontrado. Isso descarta 5
   parágrafos binários e 52 fontes que repetem um nome com outra versão.
3. Quebra cada campo de relação em cláusulas (`,`) e alternativas (`|`). De cada item
   guarda o nome, o operador e a versão; qualificadores de arquitetura (`:any`, `[amd64]`)
   e perfis de build (`<!nocheck>`) são descartados.
4. Classifica cada nome referenciado em três tipos:
   - **real**, se tem parágrafo próprio em `Packages`;
   - **virtual**, se só aparece em algum `Provides`;
   - **missing**, se não existe em `main`, por exemplo porque está em `contrib` ou
     `non-free`.
5. Grava nós e arestas no formato de importação do Neo4j.

Resultado: 68.820 pacotes reais, 65.371 virtuais, 1.147 ausentes e 37.591 fontes, ligados
por 350.996 `DEPENDS_ON`, 68.640 `PROVIDES`, 69.427 `BUILDS` e 324.236 `BUILD_DEPENDS`.

### Etapa 3: ranking (`ranking.py`)

1. **Recorte do grafo.** De `import/depends_on.csv`, usa só as arestas com `kind` igual a
   `Depends` ou `Pre-Depends` e `alt_index = 0`, ou seja, a alternativa preferida de cada
   cláusula. `Recommends` fica de fora. O grafo resultante tem 71.770 nós e 305.206
   arestas, com `A -> B` significando que A depende de B.
2. **Métricas**, calculadas para todos os nós com networkx:

   | Métrica | Cálculo |
   |---|---|
   | `pagerank` | `networkx.pagerank(G)`, com damping 0,85. Como as arestas apontam para a dependência, a importância de um pacote se propaga para aquilo de que ele depende. É o critério de ordenação. |
   | `direct_dependents` | grau de entrada do nó |
   | `transitive_dependents` | número de nós que alcançam o pacote por algum caminho (`networkx.descendants` no grafo reverso) |

3. **Ranking completo.** Ordena todos os nós por PageRank decrescente e junta os
   metadados do índice `Packages` (`source`, `version`, `section`, `description`, `Tag`,
   `homepage`). O resultado é `ranking_all.csv`, com 71.770 linhas. Nós virtuais e
   ausentes aparecem com os metadados vazios.
4. **Filtro de bibliotecas.** Mantém só os pacotes com `Section` igual a `libs` ou
   `oldlibs` (7.189 pacotes) e exclui os `*-cross` (64 pacotes), que são bibliotecas
   para compilação cruzada. O filtro de `-cross` não altera o top 100, porque o primeiro
   deles só aparece por volta da 124ª posição entre as libs, mas evita que ocupem posições
   quando o corte é maior.
5. **Corte.** Pega as 100 primeiras e numera de 1 a 100 na coluna `rank`.
6. **Categoria.** Preenche a coluna `category` a partir de
   [`classification/categories.csv`](../classification/categories.csv).

## 3. Classificação funcional (`categories.csv`)

O índice do Debian não traz a área de uso de cada lib: `Section: libs` só indica que o
pacote é uma biblioteca, e as Debtags quase nunca vão além de `role::shared-lib`. Por
isso, a categoria foi atribuída manualmente, a partir da descrição e do projeto de origem
de cada lib, com 17 categorias (descritas no README principal). O arquivo cobre as 200
primeiras libs do ranking. É uma curadoria, não um dado do Debian, e deve ser revisada.

Distribuição no top 100:

| Categoria | Libs | Categoria | Libs |
|---|---|---|---|
| `utilitarios-base` | 9 | `seguranca-autenticacao` | 6 |
| `gui-toolkit` | 8 | `parsing-formatos` | 6 |
| `runtime-c-cpp` | 7 | `texto-fontes-i18n` | 6 |
| `calculo-cientifico` | 7 | `compressao` | 5 |
| `sistema-linux` | 7 | `terminal` | 4 |
| `graficos-imagem` | 7 | `banco-de-dados` | 4 |
| `criptografia-hash` | 6 | `audio-video` | 3 |
| `linguagem-runtime` | 6 | `rede-io` | 3 |
| `janelas-x11-wayland` | 6 | | |

## 4. Reprodução

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt     # networkx 3.7, scipy 1.18.1

scripts/fetch.sh trixie amd64
shasum -a 256 data/trixie/Packages.xz data/trixie/Sources.xz   # conferir com a seção 1

.venv/bin/python -I scripts/deb2neo4j.py data/trixie/Packages data/trixie/Sources import
.venv/bin/python -I scripts/ranking.py data/trixie/Packages import results 100
```

Se os hashes forem iguais aos da seção 1, o `top100_libs.csv` gerado é idêntico ao
versionado. A execução completa leva menos de um minuto.

## 5. Limitações do critério

- **Alternativas.** Só a primeira alternativa de `a | b` conta, o que favorece a opção
  padrão do Debian.
- **Pacotes virtuais.** Dependências em pacotes virtuais (por exemplo `debconf-2.0`) não são
  repassadas aos pacotes que os provêm.
- **Variantes.** Variantes de uma mesma lib competem entre si: `libcurl4t64` (OpenSSL,
  78ª) e `libcurl3t64-gnutls` (GnuTLS, 83ª), ou Qt 5 e Qt 6.
- **Escopo.** Só entra `main` em `amd64`; `contrib`, `non-free` e outras arquiteturas
  ficam de fora.
- **Uso real.** A relevância é estrutural, medida pelo grafo de dependências declaradas.
  Não reflete quantas instalações cada pacote tem; para isso, existe o
  [popcon](https://popcon.debian.org/).
