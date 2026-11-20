#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Citizen Assist AI — protótipo de assistente de orientação cidadã (CLI).

Mobiliza conteúdos das fases 1–6: estruturas de dados, leitura JSON,
validação lógica (De Morgan — Fase 5), busca por palavras-chave,
grafo + Dijkstra (Fase 4), modelos de resposta (prompts) e métricas (Fase 6).

Execução (a partir da raiz do repositório):
    python src/sistema.py
    python3 src/sistema.py
    python3 src/sistema.py --testes
"""

from __future__ import annotations

import json
import re
import sys
import time
import unicodedata
from heapq import heappop, heappush
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Caminhos dos arquivos de dados
# ---------------------------------------------------------------------------
RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_BASE = RAIZ / "data" / "base.json"
CAMINHO_TESTES = RAIZ / "data" / "perguntas_teste.json"
CAMINHO_RESULTADOS = RAIZ / "data" / "resultados_testes.json"
CAMINHO_COMPARACAO = RAIZ / "data" / "comparacao_modelos.json"

CAMPOS_OBRIGATORIOS = (
    "id",
    "tema",
    "palavras_chave",
    "pergunta",
    "orientacao",
    "referencia",
    "data_verificacao",
)

MODELO_PADRAO = "A"
LIMIAR_SCORE = 2.0

STOPWORDS = {
    "a", "o", "as", "os", "um", "uma", "uns", "umas",
    "de", "da", "do", "das", "dos", "em", "no", "na", "nos", "nas",
    "e", "ou", "para", "por", "com", "sem", "sob", "sobre",
    "que", "qual", "quais", "como", "onde", "quando", "porque",
    "meu", "minha", "meus", "minhas", "seu", "sua", "seus", "suas",
    "ter", "tem", "tenho", "quero", "pode", "preciso", "saber",
    "eh", "ser", "sao", "esta", "este", "essa", "esse",
    "ao", "aos", "ha", "ja", "nao", "sim", "mais", "menos",
    "informacao", "informações", "informacoes",
}


# ---------------------------------------------------------------------------
# Utilitários de texto
# ---------------------------------------------------------------------------
def remover_acentos(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalizar(texto: str) -> str:
    texto = remover_acentos(texto or "").lower().strip()
    return re.sub(r"\s+", " ", texto)


def tokenizar(texto: str) -> list[str]:
    texto = normalizar(texto)
    tokens = re.findall(r"[a-z0-9]{2,}", texto)
    return [t for t in tokens if t not in STOPWORDS]


# ---------------------------------------------------------------------------
# Carregamento e validação da base
# ---------------------------------------------------------------------------
def carregar_base(caminho: Path = CAMINHO_BASE) -> dict[str, Any]:
    if not caminho.exists():
        raise FileNotFoundError(
            f"Base de conhecimento não encontrada em: {caminho}\n"
            "Verifique se o arquivo data/base.json existe."
        )

    try:
        with caminho.open("r", encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
    except json.JSONDecodeError as erro:
        raise ValueError(f"Arquivo JSON inválido: {erro}") from erro

    if not isinstance(dados, dict) or not dados:
        raise ValueError("Base vazia ou em formato inesperado (esperado objeto JSON).")

    orientacoes = dados.get("orientacoes")
    if not isinstance(orientacoes, list) or len(orientacoes) == 0:
        raise ValueError("Campo 'orientacoes' ausente ou vazio na base.")

    validas: list[dict[str, Any]] = []
    for indice, item in enumerate(orientacoes):
        if not isinstance(item, dict):
            print(f"[aviso] Registro {indice} ignorado: não é um objeto.")
            continue
        faltando = [c for c in CAMPOS_OBRIGATORIOS if c not in item or item[c] in (None, "")]
        if faltando:
            print(f"[aviso] Registro {item.get('id', indice)} incompleto: {faltando}. Ignorado.")
            continue
        if not isinstance(item["palavras_chave"], list):
            print(f"[aviso] Registro {item['id']}: palavras_chave deve ser lista. Ignorado.")
            continue
        validas.append(item)

    if not validas:
        raise ValueError("Nenhuma orientação válida encontrada após validação dos campos.")

    dados["orientacoes"] = validas

    if "grafo_temas" not in dados or not isinstance(dados["grafo_temas"], dict):
        temas = sorted({o["tema"] for o in validas})
        grafo = {t: {} for t in temas}
        for i, t1 in enumerate(temas):
            for t2 in temas[i + 1 :]:
                grafo[t1][t2] = 2
                grafo[t2][t1] = 2
        dados["grafo_temas"] = grafo

    # Grafo de navegação (tema + subtema). Fase 4: caminhos multi-hop com Dijkstra.
    if "grafo_navegacao" not in dados or not isinstance(dados["grafo_navegacao"], dict):
        dados["grafo_navegacao"] = dict(dados["grafo_temas"])

    return dados


def indexar_por_id(orientacoes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Dicionário id -> orientação para acesso O(1)."""
    return {item["id"]: item for item in orientacoes}


def indexar_por_subtema(orientacoes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Primeira orientação de cada subtema (para sugestões de continuidade)."""
    mapa: dict[str, dict[str, Any]] = {}
    for item in orientacoes:
        sub = item.get("subtema")
        if sub and sub not in mapa:
            mapa[sub] = item
    return mapa


def agrupar_por_tema(orientacoes: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grupos: dict[str, list[dict[str, Any]]] = {}
    for item in orientacoes:
        grupos.setdefault(item["tema"], []).append(item)
    return grupos


# ---------------------------------------------------------------------------
# Validação de entrada (lógica booleana / De Morgan — Fase 5)
# ---------------------------------------------------------------------------
def entrada_valida(texto: str) -> tuple[bool, str]:
    """
    Regra positiva: válida ⇔ (não_vazia) ∧ (tem_alfanumérico)
    Por De Morgan: inválida ⇔ (vazia) ∨ (sem_alfanumérico)
    """
    bruto = texto if texto is not None else ""
    so_espacos = bruto.strip() == ""
    tem_alfa = bool(re.search(r"[A-Za-zÀ-ÿ0-9]", bruto))

    if so_espacos or (not tem_alfa):
        if so_espacos:
            return False, "Entrada vazia. Digite uma pergunta ou escolha uma opção do menu."
        return False, "Entrada inválida (apenas símbolos). Use palavras ou números."

    return True, ""


# ---------------------------------------------------------------------------
# Busca por palavras-chave (+ sinônimos)
# ---------------------------------------------------------------------------
def _termos_do_item(item: dict[str, Any]) -> list[str]:
    termos = list(item.get("palavras_chave", []))
    termos.extend(item.get("sinonimos", []) or [])
    return [str(t) for t in termos]


def pontuar_orientacao(consulta: str, item: dict[str, Any]) -> float:
    tokens_consulta = set(tokenizar(consulta))
    if not tokens_consulta:
        return 0.0

    score_chave = 0.0
    for palavra in _termos_do_item(item):
        tokens_chave = set(tokenizar(palavra))
        if tokens_chave & tokens_consulta:
            score_chave += 3.0
        elif normalizar(palavra) and normalizar(palavra) in normalizar(consulta):
            score_chave += 3.0

    tokens_pergunta = set(tokenizar(item.get("pergunta", "")))
    score_pergunta = 1.5 * len(tokens_consulta & tokens_pergunta)

    tokens_orientacao = set(tokenizar(item.get("orientacao", "")))
    score_texto = 0.25 * len(tokens_consulta & tokens_orientacao)

    if score_chave == 0.0 and score_pergunta == 0.0:
        return 0.0

    return score_chave + score_pergunta + score_texto


def buscar_orientacoes(
    consulta: str,
    orientacoes: list[dict[str, Any]],
    limiar: float = LIMIAR_SCORE,
    limite: int = 5,
    tema_filtro: str | None = None,
) -> list[tuple[float, dict[str, Any]]]:
    universo = orientacoes
    if tema_filtro:
        universo = [o for o in orientacoes if o["tema"] == tema_filtro]

    pontuados: list[tuple[float, dict[str, Any]]] = []
    for item in universo:
        score = pontuar_orientacao(consulta, item)
        if score >= limiar:
            pontuados.append((score, item))

    pontuados.sort(key=lambda x: (-x[0], x[1]["id"]))
    return pontuados[:limite]


def classificar_resultado(resultados: list[tuple[float, dict[str, Any]]]) -> str:
    if not resultados:
        return "nenhum"
    if len(resultados) == 1:
        return "unico"
    # Ambiguidade se o 2º colocado estiver a menos de 4 pontos do 1º
    melhor = resultados[0][0]
    proximos = [r for r in resultados if melhor - r[0] < 4.0]
    if len(proximos) >= 2:
        return "multiplo"
    return "unico"


# ---------------------------------------------------------------------------
# Grafo + Dijkstra (Fase 4)
# ---------------------------------------------------------------------------
def dijkstra(
    grafo: dict[str, dict[str, float | int]],
    origem: str,
    destino: str,
) -> tuple[list[str], float] | tuple[None, None]:
    """Menor caminho ponderado entre nós do grafo de navegação."""
    if origem not in grafo or destino not in grafo:
        return None, None

    distancias = {no: float("inf") for no in grafo}
    anteriores: dict[str, str | None] = {no: None for no in grafo}
    distancias[origem] = 0.0
    fila: list[tuple[float, str]] = [(0.0, origem)]

    while fila:
        custo_atual, no = heappop(fila)
        if custo_atual > distancias[no]:
            continue
        if no == destino:
            break
        for vizinho, peso in grafo.get(no, {}).items():
            if vizinho not in distancias:
                continue
            novo = custo_atual + float(peso)
            if novo < distancias[vizinho]:
                distancias[vizinho] = novo
                anteriores[vizinho] = no
                heappush(fila, (novo, vizinho))

    if distancias[destino] == float("inf"):
        return None, None

    caminho: list[str] = []
    atual: str | None = destino
    while atual is not None:
        caminho.append(atual)
        atual = anteriores[atual]
    caminho.reverse()
    return caminho, distancias[destino]


def nos_relacionados(
    grafo: dict[str, dict[str, float | int]],
    no: str,
    limite: int = 4,
) -> list[tuple[str, float]]:
    if no not in grafo:
        return []
    vizinhos = [(v, float(p)) for v, p in grafo[no].items()]
    vizinhos.sort(key=lambda x: x[1])
    return vizinhos[:limite]


def sugerir_navegacao(
    base: dict[str, Any],
    tema_atual: str | None = None,
    subtema_atual: str | None = None,
) -> None:
    """Sugere continuidade via vizinhos e caminho Dijkstra multi-hop."""
    grafo = base.get("grafo_navegacao") or base["grafo_temas"]
    por_sub = indexar_por_subtema(base["orientacoes"])
    ancora = subtema_atual or tema_atual

    if not ancora or ancora not in grafo:
        print("\nNós disponíveis no grafo de navegação (temas e subtemas):")
        for no in sorted(grafo.keys()):
            print(f"  - {no}")
        return

    print(f"\n--- Continuação da consulta (nó: {ancora}) ---")
    relacionados = nos_relacionados(grafo, ancora)
    if relacionados:
        print("Assuntos / subtemas relacionados (menor custo = mais próximo):")
        for no, peso in relacionados:
            extra = ""
            if no in por_sub:
                extra = f" → {por_sub[no]['id']}: {por_sub[no]['pergunta']}"
            print(f"  -> {no} (custo {peso}){extra}")

    # Destino multi-hop demonstrativo (Fase 4): preferir caminho com >= 2 arestas
    candidatos_destino = [n for n in grafo if n != ancora]
    melhor: tuple[list[str], float] | None = None
    for dest in candidatos_destino:
        caminho, custo = dijkstra(grafo, ancora, dest)
        if not caminho or custo is None:
            continue
        if len(caminho) >= 3:  # origem + >=1 intermediário + destino
            if melhor is None or custo < melhor[1]:
                melhor = (caminho, float(custo))
    if melhor is None:
        for dest in candidatos_destino:
            caminho, custo = dijkstra(grafo, ancora, dest)
            if caminho and custo is not None:
                melhor = (caminho, float(custo))
                break

    if melhor:
        caminho, custo = melhor
        print(
            f"Caminho sugerido (Dijkstra): {' > '.join(caminho)} "
            f"(custo total {custo}; {len(caminho) - 1} aresta(s))"
        )


# ---------------------------------------------------------------------------
# Modelos de prompt / formatação de resposta
# ---------------------------------------------------------------------------
def formatar_resposta(item: dict[str, Any], modelo: str = MODELO_PADRAO) -> str:
    """
    Modelo A (completo): papel + orientação + fonte + aviso.
    Modelo B (curto): orientação + fonte.
    """
    modelo = (modelo or "A").upper()
    orientacao = item["orientacao"]
    referencia = item["referencia"]
    data = item["data_verificacao"]
    aviso_extra = ""
    if item.get("requer_confirmacao"):
        aviso_extra = (
            "\n[Confirmação] Esta orientação pode exigir requisitos atualizados. "
            "Confira a fonte oficial antes de agir."
        )

    if modelo == "B":
        return (
            f"Orientação: {orientacao}\n"
            f"Fonte: {referencia} (verificada em {data})"
            f"{aviso_extra}"
        )

    return (
        "Sou o Citizen Assist AI, um assistente introdutório de orientação cidadã.\n"
        "Não substituo canais oficiais de órgãos públicos.\n\n"
        f"Sobre: {item['pergunta']}\n"
        f"Orientação: {orientacao}\n"
        f"Fonte consultada: {referencia}\n"
        f"Data de verificação: {data}"
        f"{aviso_extra}\n\n"
        "Sempre confirme as informações no site oficial antes de tomar decisões."
    )


def mensagem_sem_correspondencia(
    consulta: str,
    base: dict[str, Any],
) -> str:
    por_tema = agrupar_por_tema(base["orientacoes"])
    temas = ", ".join(sorted(por_tema.keys()))
    linhas = [
        f'Não encontrei uma orientação confiável para: "{consulta}".',
        "Não invento instruções fora da base verificada.",
        f"Temas disponíveis: {temas}.",
        "Tente reformular com palavras-chave (ex.: CPF, INSS, Procon) ou escolha um tema no menu.",
        "",
        "Sugestões iniciais por tema:",
    ]
    for tema in sorted(por_tema.keys())[:3]:
        amostra = por_tema[tema][:1]
        for item in amostra:
            linhas.append(f"  - [{tema}] {item['id']}: {item['pergunta']}")
    return "\n".join(linhas)


# ---------------------------------------------------------------------------
# Camada de consulta
# ---------------------------------------------------------------------------
def consultar(
    pergunta: str,
    base: dict[str, Any],
    modelo: str = MODELO_PADRAO,
    interativo: bool = True,
    tema_filtro: str | None = None,
) -> dict[str, Any]:
    inicio = time.perf_counter()
    ok, motivo = entrada_valida(pergunta)
    if not ok:
        return {
            "status": "erro_entrada",
            "mensagem": motivo,
            "ids": [],
            "candidatos": [],
            "tempo_s": time.perf_counter() - inicio,
        }

    orientacoes = base["orientacoes"]
    resultados = buscar_orientacoes(pergunta, orientacoes, tema_filtro=tema_filtro)
    classe = classificar_resultado(resultados)

    if classe == "nenhum":
        texto = mensagem_sem_correspondencia(pergunta, base)
        return {
            "status": "sem_correspondencia",
            "mensagem": texto,
            "ids": [],
            "candidatos": [],
            "tema": None,
            "subtema": None,
            "tempo_s": time.perf_counter() - inicio,
        }

    if classe == "multiplo" and interativo:
        print("\nEncontrei mais de uma orientação possível (ambiguidade):")
        for i, (score, item) in enumerate(resultados, start=1):
            print(f"  [{i}] ({item['id']}) {item['pergunta']}  [score={score:.1f}]")
        escolha = input("Escolha o número (ou Enter para o primeiro): ").strip()
        indice = 0
        if escolha.isdigit():
            num = int(escolha)
            if 1 <= num <= len(resultados):
                indice = num - 1
        escolhido = resultados[indice][1]
        status = "ambiguo_resolvido"
    else:
        escolhido = resultados[0][1]
        status = "ok" if classe == "unico" else "ambiguo"

    texto = formatar_resposta(escolhido, modelo=modelo)
    return {
        "status": status,
        "mensagem": texto,
        "ids": [escolhido["id"]],
        "candidatos": [r[1]["id"] for r in resultados],
        "tema": escolhido["tema"],
        "subtema": escolhido.get("subtema"),
        "item": escolhido,
        "tempo_s": time.perf_counter() - inicio,
    }


# ---------------------------------------------------------------------------
# Testes e métricas
# ---------------------------------------------------------------------------
def carregar_perguntas_teste(caminho: Path = CAMINHO_TESTES) -> list[dict[str, Any]]:
    if not caminho.exists():
        raise FileNotFoundError(f"Arquivo de testes não encontrado: {caminho}")
    with caminho.open("r", encoding="utf-8") as arquivo:
        dados = json.load(arquivo)
    return dados.get("perguntas", [])


def avaliar_caso(caso: dict[str, Any], resultado: dict[str, Any]) -> bool:
    """Critérios estritos — evita inflar a taxa de acerto."""
    status = resultado["status"]
    ids = resultado.get("ids") or []
    candidatos = resultado.get("candidatos") or []

    if caso.get("espera_erro"):
        return status == "erro_entrada"

    if caso.get("espera_sem_correspondencia"):
        return status == "sem_correspondencia"

    if caso.get("espera_ambiguo_ou_multiplo"):
        # Acerto somente com ambiguidade real: status ambíguo OU >= 2 candidatos
        return status in ("ambiguo", "ambiguo_resolvido") or len(candidatos) >= 2

    esperado = caso.get("id_esperado")
    if esperado:
        return esperado in ids

    return False


def _texto_esperado(caso: dict[str, Any], por_id: dict[str, dict[str, Any]]) -> str:
    if caso.get("comportamento_esperado"):
        return str(caso["comportamento_esperado"])
    esperado = caso.get("id_esperado")
    if esperado and esperado in por_id:
        item = por_id[esperado]
        return f"{esperado}: {item['pergunta']} | {item['orientacao'][:160]}..."
    if caso.get("espera_erro"):
        return "erro_entrada"
    if caso.get("espera_sem_correspondencia"):
        return "sem_correspondencia"
    if caso.get("espera_ambiguo_ou_multiplo"):
        return "ambiguidade (>=2 candidatos)"
    return "—"


def _texto_obtido(resultado: dict[str, Any]) -> str:
    msg = (resultado.get("mensagem") or "").replace("\n", " | ")
    if len(msg) > 280:
        msg = msg[:277] + "..."
    cands = resultado.get("candidatos") or []
    return (
        f"status={resultado.get('status')}; ids={resultado.get('ids')}; "
        f"candidatos={cands}; texto={msg}"
    )


def executar_testes(
    base: dict[str, Any],
    modelo: str = MODELO_PADRAO,
    salvar: bool = True,
) -> dict[str, Any]:
    casos = carregar_perguntas_teste()
    por_id = indexar_por_id(base["orientacoes"])
    registros: list[dict[str, Any]] = []
    acertos = 0
    tempos: list[float] = []

    print("\n=== Executando bateria de testes ===\n")
    for caso in casos:
        resultado = consultar(
            caso.get("pergunta", ""),
            base,
            modelo=modelo,
            interativo=False,
        )
        acerto = avaliar_caso(caso, resultado)
        if acerto:
            acertos += 1
        tempos.append(resultado["tempo_s"])
        marca = "ACERTO" if acerto else "ERRO"
        print(
            f"[{caso['id']}] {marca} | status={resultado['status']} | "
            f"ids={resultado.get('ids')} | candidatos={resultado.get('candidatos')} | "
            f"tempo={resultado['tempo_s']*1000:.2f} ms"
        )
        registros.append(
            {
                "id_teste": caso["id"],
                "pergunta": caso.get("pergunta"),
                "tipo": caso.get("tipo"),
                "esperado_id": caso.get("id_esperado"),
                "resposta_esperada": _texto_esperado(caso, por_id),
                "resposta_obtida": _texto_obtido(resultado),
                "obtido_ids": resultado.get("ids"),
                "candidatos": resultado.get("candidatos"),
                "status": resultado["status"],
                "acerto": acerto,
                "tempo_s": round(resultado["tempo_s"], 6),
            }
        )

    total = len(casos) or 1
    taxa = (acertos / total) * 100.0
    tempo_medio = sum(tempos) / len(tempos) if tempos else 0.0

    resumo = {
        "modelo_resposta": modelo,
        "total_testes": total,
        "acertos": acertos,
        "erros": total - acertos,
        "taxa_acerto_percentual": round(taxa, 2),
        "tempo_medio_s": round(tempo_medio, 6),
        "tempo_medio_ms": round(tempo_medio * 1000, 3),
        "observacao": (
            "Taxa calculada com critérios estritos (ambiguidade exige >=2 candidatos). "
            "Valores próximos de 100% em base pequena devem ser interpretados com cautela."
        ),
        "registros": registros,
    }

    print("\n--- Indicadores ---")
    print(f"Total: {total} | Acertos: {acertos} | Erros: {total - acertos}")
    print(f"Taxa de acerto: {resumo['taxa_acerto_percentual']}%")
    print(f"Tempo médio de consulta: {resumo['tempo_medio_ms']} ms")

    if salvar:
        with CAMINHO_RESULTADOS.open("w", encoding="utf-8") as arquivo:
            json.dump(resumo, arquivo, ensure_ascii=False, indent=2)
        print(f"\nResultados salvos em: {CAMINHO_RESULTADOS}")

    return resumo


def _nota_rubrica_resposta(texto: str, modelo: str) -> dict[str, int]:
    """Rubrica qualitativa 0–2 por critério (não mede recuperação de id)."""
    t = texto.lower()
    clareza = 2 if len(texto) > 80 else 1
    citacao = 2 if ("fonte" in t or "http" in t) else 0
    aviso = 2 if ("não substituo" in t or "nao substituo" in t or "não é um canal" in t
                  or "nao e um canal" in t or "oficial" in t) else (
        1 if "confirmação" in t or "confirmacao" in t else 0
    )
    completude = 2 if modelo.upper() == "A" and "sou o citizen" in t else (
        1 if "orientação" in t or "orientacao" in t else 0
    )
    return {
        "clareza": clareza,
        "citacao_fonte": citacao,
        "aviso_limite": aviso,
        "completude": completude,
    }


def comparar_modelos(base: dict[str, Any]) -> None:
    """Compara A vs B: taxa de id (igual por construção) + rubrica qualitativa."""
    print("\n=== Comparação de modelos de resposta ===")
    resumo_a = executar_testes(base, modelo="A", salvar=True)

    amostras = [
        "Como consultar meu CPF?",
        "Como criar conta no gov.br?",
        "Quando procurar o Procon?",
        "Como tirar o cartão SUS?",
        "Para que serve o Disque 100?",
    ]

    detalhes: list[dict[str, Any]] = []
    soma_a = {"clareza": 0, "citacao_fonte": 0, "aviso_limite": 0, "completude": 0}
    soma_b = {"clareza": 0, "citacao_fonte": 0, "aviso_limite": 0, "completude": 0}

    for pergunta in amostras:
        ra = consultar(pergunta, base, modelo="A", interativo=False)
        rb = consultar(pergunta, base, modelo="B", interativo=False)
        na = _nota_rubrica_resposta(ra.get("mensagem", ""), "A")
        nb = _nota_rubrica_resposta(rb.get("mensagem", ""), "B")
        for k in soma_a:
            soma_a[k] += na[k]
            soma_b[k] += nb[k]
        detalhes.append(
            {
                "pergunta": pergunta,
                "id_recuperado_a": ra.get("ids"),
                "id_recuperado_b": rb.get("ids"),
                "notas_a": na,
                "notas_b": nb,
                "total_a": sum(na.values()),
                "total_b": sum(nb.values()),
            }
        )

    n = len(amostras) or 1
    media_a = {k: round(v / n, 2) for k, v in soma_a.items()}
    media_b = {k: round(v / n, 2) for k, v in soma_b.items()}
    total_a = round(sum(media_a.values()), 2)
    total_b = round(sum(media_b.values()), 2)

    justificativa = (
        "A recuperação do id é a mesma nos dois modelos (o template não altera a busca). "
        "Na rubrica qualitativa (clareza, citação, aviso de limite, completude), "
        f"o Modelo A soma {total_a}/8 em média e o Modelo B soma {total_b}/8. "
        "O Modelo A é o padrão por incluir papel do assistente e aviso explícito de "
        "não oficialidade, mais adequado à orientação cidadã responsável."
    )

    comparacao = {
        "criterios": ["clareza", "citacao_fonte", "aviso_limite", "completude"],
        "escala": "0 a 2 por critério",
        "amostras": detalhes,
        "medias_a": media_a,
        "medias_b": media_b,
        "total_medio_a": total_a,
        "total_medio_b": total_b,
        "taxa_id_modelo_a": resumo_a["taxa_acerto_percentual"],
        "modelo_padrao": "A",
        "justificativa": justificativa,
    }

    with CAMINHO_COMPARACAO.open("w", encoding="utf-8") as arquivo:
        json.dump(comparacao, arquivo, ensure_ascii=False, indent=2)

    print(f"\nRubrica qualitativa (média /2 por critério, {n} perguntas):")
    print(f"  Modelo A: {media_a} | total {total_a}/8")
    print(f"  Modelo B: {media_b} | total {total_b}/8")
    print(f"Taxa de acerto de id (Modelo A): {resumo_a['taxa_acerto_percentual']}%")
    print(justificativa)
    print(f"Comparação salva em: {CAMINHO_COMPARACAO}")
    print("Padrão do sistema: Modelo A.")


# ---------------------------------------------------------------------------
# Interface de menu (CLI)
# ---------------------------------------------------------------------------
def exibir_cabecalho(base: dict[str, Any] | None = None) -> None:
    print("\n" + "=" * 60)
    print("  Citizen Assist AI — Orientação cidadã (protótipo)")
    aviso = (base or {}).get("aviso_geral") or (
        "NÃO é canal oficial. Confirme sempre nas fontes citadas."
    )
    print(f"  {aviso}")
    print("=" * 60)


def listar_temas(base: dict[str, Any]) -> None:
    por_tema = agrupar_por_tema(base["orientacoes"])
    print("\nTemas disponíveis:")
    for i, tema in enumerate(sorted(por_tema.keys()), start=1):
        print(f"  [{i}] {tema} ({len(por_tema[tema])} orientações)")


def _resolver_tema(escolha: str, temas: list[str]) -> str | None:
    if escolha.isdigit():
        idx = int(escolha) - 1
        if 0 <= idx < len(temas):
            return temas[idx]
        return None
    chave = normalizar(escolha).replace(" ", "_")
    for t in temas:
        if normalizar(t) == chave or chave in normalizar(t):
            return t
    return None


def menu_por_tema(base: dict[str, Any], modelo: str) -> None:
    por_tema = agrupar_por_tema(base["orientacoes"])
    temas = sorted(por_tema.keys())
    listar_temas(base)
    escolha = input("\nDigite o número ou o nome do tema: ").strip()
    tema = _resolver_tema(escolha, temas)
    if tema is None:
        print("Opção inexistente. Volte ao menu e tente novamente.")
        return

    print(f"\nOrientações do tema '{tema}':")
    itens = por_tema[tema]
    for i, item in enumerate(itens, start=1):
        print(f"  [{i}] {item['id']} — {item['pergunta']}")

    sub = input("Escolha o número da orientação (ou Enter para voltar): ").strip()
    if not sub:
        return
    if not sub.isdigit() or not (1 <= int(sub) <= len(itens)):
        print("Opção inexistente.")
        return

    item = itens[int(sub) - 1]
    print("\n" + formatar_resposta(item, modelo=modelo))
    sugerir_navegacao(base, tema_atual=tema, subtema_atual=item.get("subtema"))


def menu_busca(base: dict[str, Any], modelo: str, com_filtro: bool = False) -> None:
    tema_filtro = None
    if com_filtro:
        temas = sorted(agrupar_por_tema(base["orientacoes"]).keys())
        listar_temas(base)
        escolha = input("Filtrar por tema (número/nome, ou Enter para todos): ").strip()
        if escolha:
            tema_filtro = _resolver_tema(escolha, temas)
            if tema_filtro is None:
                print("Tema inválido; buscando em toda a base.")
                tema_filtro = None

    pergunta = input("\nDigite sua pergunta: ")
    resultado = consultar(
        pergunta, base, modelo=modelo, interativo=True, tema_filtro=tema_filtro
    )
    print("\n" + resultado["mensagem"])
    if resultado.get("tema"):
        sugerir_navegacao(
            base,
            tema_atual=resultado.get("tema"),
            subtema_atual=resultado.get("subtema"),
        )
    elif resultado["status"] == "sem_correspondencia":
        sugerir_navegacao(base, tema_atual=None)


def menu_grafo(base: dict[str, Any]) -> None:
    grafo = base.get("grafo_navegacao") or base["grafo_temas"]
    nos = sorted(grafo.keys())
    print("\nNavegação por grafo (temas e subtemas) — Dijkstra (Fase 4)")
    print("Exemplos multi-hop: cpf → govbr → inss | cadunico → cras → acessibilidade")
    for i, no in enumerate(nos, start=1):
        print(f"  [{i}] {no}")

    origem_raw = input("Nó de origem (número ou nome): ").strip()
    destino_raw = input("Nó de destino (número ou nome): ").strip()

    def resolver(valor: str) -> str | None:
        if valor.isdigit():
            idx = int(valor) - 1
            if 0 <= idx < len(nos):
                return nos[idx]
            return None
        chave = normalizar(valor).replace(" ", "_")
        for t in nos:
            if normalizar(t) == chave:
                return t
        return None

    origem = resolver(origem_raw)
    destino = resolver(destino_raw)
    if origem is None or destino is None:
        print("Nó inválido. Use um dos nós listados.")
        return

    caminho, custo = dijkstra(grafo, origem, destino)
    if not caminho:
        print("Não há caminho entre esses nós.")
        return
    print(f"\nCaminho: {' > '.join(caminho)}")
    print(f"Custo total: {custo} | Arestas: {len(caminho) - 1}")
    por_sub = indexar_por_subtema(base["orientacoes"])
    for no in caminho:
        if no in por_sub:
            print(f"  • {no}: {por_sub[no]['id']} — {por_sub[no]['pergunta']}")


def menu_principal(base: dict[str, Any]) -> None:
    modelo = MODELO_PADRAO
    while True:
        exibir_cabecalho(base)
        print(f"Modelo de resposta atual: {modelo}")
        print(
            """
[1] Listar / consultar por tema
[2] Buscar por pergunta
[3] Buscar com filtro de tema
[4] Navegar grafo (Dijkstra — temas/subtemas)
[5] Executar testes e métricas
[6] Comparar modelos de resposta (A vs B)
[7] Alternar modelo de resposta (A/B)
[0] Sair
"""
        )
        opcao = input("Escolha uma opção: ").strip()

        if opcao == "1":
            menu_por_tema(base, modelo)
        elif opcao == "2":
            menu_busca(base, modelo, com_filtro=False)
        elif opcao == "3":
            menu_busca(base, modelo, com_filtro=True)
        elif opcao == "4":
            menu_grafo(base)
        elif opcao == "5":
            executar_testes(base, modelo=modelo, salvar=True)
        elif opcao == "6":
            comparar_modelos(base)
        elif opcao == "7":
            modelo = "B" if modelo == "A" else "A"
            print(f"Modelo alterado para: {modelo}")
        elif opcao == "0":
            print("Encerrando. Confirme sempre as informações nas fontes oficiais.")
            break
        else:
            print("Opção inexistente. Digite um número do menu.")

        input("\nPressione Enter para continuar...")


def main() -> int:
    try:
        base = carregar_base()
    except (FileNotFoundError, ValueError) as erro:
        print(f"[erro] {erro}")
        return 1

    if len(sys.argv) > 1 and sys.argv[1] in ("--testes", "--test", "-t"):
        executar_testes(base, modelo=MODELO_PADRAO, salvar=True)
        return 0

    if len(sys.argv) > 1 and sys.argv[1] in ("--comparar", "--compare"):
        comparar_modelos(base)
        return 0

    print(
        f"Base carregada: {len(base['orientacoes'])} orientações | "
        f"temas: {', '.join(sorted({o['tema'] for o in base['orientacoes']}))}"
    )
    menu_principal(base)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
