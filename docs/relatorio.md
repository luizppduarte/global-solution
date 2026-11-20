# Relatório — Citizen Assist AI  
## Global Solution 2026.2 | CitizenTech / Citizen Assist

**Integrante:** Luiz Duarte — RM 568970  
**Curso:** Ciência da Computação (FIAP ON)  
**Execução do protótipo:** `python src/sistema.py` ou `python3 src/sistema.py`

---

## 1. Problema e motivação

Cidadãos frequentemente encontram orientações fragmentadas sobre documentos, serviços públicos e direitos. Termos técnicos, portais distintos e instruções incompletas aumentam o tempo de busca e o risco de interpretação incorreta.

O desafio *Citizen Assist AI* propõe um assistente digital introdutório que organiza informações **verificadas**, responde consultas simples com **referência** e declara **limites** quando a base não é suficiente — sem se apresentar como canal oficial.

---

## 2. Público beneficiado e temas

**Público.** Pessoas em busca de orientação inicial (estudantes, famílias, usuários de serviços socioassistenciais e de consumo), com ênfase em clareza e responsabilidade.

**Temas (≥3):**

1. **Documentação** — CPF, CIN/RG, título eleitoral, CNH, CTPS digital, conta gov.br.  
2. **Serviços públicos** — CadÚnico, Bolsa Família, INSS, Cartão SUS, Consumidor.gov.br.  
3. **Orientação comunitária** — Procon, Disque 100, Ligue 180, CRAS, educação/EJA, inclusão (LBI).

A base possui **17 orientações**, cada uma com identificador, subtema, palavras-chave, sinônimos, texto resumido, URL e data de verificação.

---

## 3. Arquitetura da solução

O protótipo é uma aplicação **textual (CLI)** em Python, usando apenas a biblioteca padrão.

```text
Usuário (menu / pergunta / filtro de tema)
        │
        ▼
┌───────────────────┐
│  Validação lógica │  (vazio, símbolos, De Morgan — Fase 5)
└─────────┬─────────┘
          ▼
┌───────────────────┐     data/base.json
│  Busca por score  │◄──── listas + dicionários + sinônimos
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ Templates A/B     │  (prompts de resposta)
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ Grafo navegação   │  tema + subtema → Dijkstra multi-hop (Fase 4)
└───────────────────┘
          │
          ▼
   Testes + rubrica A/B → resultados_testes.json / comparacao_modelos.json
```

**Decisão de projeto:** sem API de LLM em tempo de execução. Estratégias de prompt aparecem como **modelos de instrução** determinísticos, confrontados com a base verificada.

---

## 4. Fontes e organização da base

Orientações redigidas como resumos introdutórios e ancoradas em portais públicos (Receita Federal, TSE, gov.br, DETRAN/CNH, Trabalho, MDS, INSS, CNS/Saúde, Consumidor.gov.br, MDH, MEC). Cada registro traz `data_verificacao`.

Regras de qualidade:

- Não inventar taxas, prazos municipais ou passos não confirmados.  
- Marcar `requer_confirmacao` quando o procedimento varia por estado/cidade.  
- Exibir `aviso_geral` no cabeçalho do programa.  
- Campo `sinonimos` para reformulações sem reescrever o algoritmo.

---

## 5. Estratégias de busca, grafo e lógica

### 5.1 Busca

1. Normalização (caixa, acentos) e tokenização com stopwords.  
2. Score: palavras-chave e sinônimos (peso alto) + tokens da pergunta + leve reforço do texto.  
3. Sem overlap útil com chave/pergunta → score zero.  
4. Scores próximos → classificação **ambígua** e escolha do usuário (modo interativo).  
5. Opção de **filtro por tema** antes da busca.

### 5.2 Grafo e Dijkstra (Fase 4)

Além do grafo de três temas, `grafo_navegacao` inclui **subtemas** com arestas cruzadas (ex.: `cpf → govbr → inss`, `cadunico → cras`). O Dijkstra calcula o menor custo; a interface destaca caminhos com **duas ou mais arestas**, evitando um Dijkstra apenas decorativo.

Após cada resposta, o sistema sugere nós vizinhos e, quando possível, a orientação correspondente (`id` + pergunta).

### 5.3 Validação e De Morgan (Fase 5)

Regra positiva: válida ⇔ (não vazia) ∧ (possui alfanumérico).  
Por De Morgan: inválida ⇔ (vazia) ∨ (sem alfanumérico).

### 5.4 Mapa de Karnaugh (simplificação conceitual)

| V (vazia) | S (sem alfanumérico) | Inválida? |
|-----------|----------------------|-----------|
| 0 | 0 | 0 |
| 0 | 1 | 1 |
| 1 | 0 | 1 |
| 1 | 1 | 1 |

Simplificação: Inválida = V ∨ S.

---

## 6. Estratégias de prompt / modelos de resposta

| Modelo | Instrução | Uso |
|--------|-----------|-----|
| **A** | Papel + orientação + fonte + data + aviso de não oficialidade | Padrão |
| **B** | Orientação + fonte | Consulta rápida |

A recuperação do *id* é idêntica (o template não altera a busca). A comparação relevante é **qualitativa**, com rubrica 0–2 em clareza, citação de fonte, aviso de limite e completude (`data/comparacao_modelos.json`):

- Modelo A: **8,0 / 8**  
- Modelo B: **6,2 / 8**  

Justificativa: o Modelo A comunica melhor o papel e os limites do assistente.

---

## 7. Testes e indicadores

### 7.1 Plano de testes

Arquivo `data/perguntas_teste.json`: diretas, reformulações, fora de tema, vazio, símbolos e ambiguidade controlada (T16: identidade + trabalho).

Critérios **estritos:** ambiguidade só conta como acerto com `status` ambíguo ou ≥2 candidatos; casos com `id_esperado` exigem o id no topo (`ids`).

### 7.2 Resultados

| Indicador | Valor |
|-----------|-------|
| Total de casos | 16 |
| Acertos | 16 |
| Taxa de acerto | **100%** (critérios estritos) |
| Tempo médio | **~1,5 ms** |
| T16 | `status=ambiguo`; candidatos DOC-005, DOC-002, DOC-004 |

Cada registro em `resultados_testes.json` guarda `resposta_esperada`, `resposta_obtida`, `acerto` e `tempo_s`.

**Interpretação:** a taxa alta reflete alinhamento testes↔base e amostra pequena. Em produção, linguagem coloquial reduziria o acerto — daí a ênfase em sinônimos e filtro por tema.

### 7.3 Melhorias futuras

1. Ampliar sinônimos regionais.  
2. Teste com usuário do público-alvo.  
3. Modo leitura simplificada / acessibilidade.

---

## 8. Impacto social e responsabilidade

O assistente pode reduzir o tempo até a primeira orientação útil, apontando o portal correto. O impacto positivo depende de transparência (fontes e datas), honestidade sobre limites, privacidade (sem coleta de dados pessoais) e de não confundir o usuário com atendimento governamental oficial.

---

## 9. Conteúdos das fases mobilizados

| Fases | Aplicação no projeto |
|-------|----------------------|
| 1–3 | Python, listas/dicionários, lógica, pensamento computacional |
| 4 | Organização de dados, grafo tema/subtema, Dijkstra multi-hop |
| 5 | JSON, sinônimos, modelos de instrução/prompts, De Morgan |
| 6 | Assistente virtual, busca/comparação, métricas e rubrica qualitativa |

---

## 10. Conclusões

O *Citizen Assist AI* cumpre o objetivo de protótipo funcional com maior rigor metodológico: critérios de teste honestos, registro esperado/obtido, grafo com caminhos multi-hop e comparação A/B qualitativa. Próximos passos: cobertura local, sinônimos e revisão periódica das URLs oficiais.

---

## Referências (seleção)

- Portal gov.br e Conta gov.br  
- Receita Federal — CPF  
- TSE — Título eleitoral  
- gov.br — renovação de CNH / Carteira de Trabalho Digital  
- MDS — Cadastro Único / Bolsa Família / SUAS (CRAS)  
- INSS — Meu INSS / gov.br  
- Ministério da Saúde — Cartão Nacional de Saúde (CNS)  
- Consumidor.gov.br e defesa do consumidor (MJ)  
- Ministério dos Direitos Humanos — Disque 100 / Ligue 180 / PcD  
- MEC — informações educacionais  

URLs completas constam em cada registro de `data/base.json`.
