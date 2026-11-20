# Citizen Assist AI — Global Solution 2026.2

Assistente digital introdutório (CLI em Python) para orientação cidadã: consulta uma base verificada, apresenta respostas com fontes e informa limites quando não há informação suficiente.

> **Aviso:** este protótipo **não** é um canal oficial de órgãos públicos. Confirme sempre as informações nas fontes citadas.

---

## Integrantes

| Nome | RM |
|------|----|
| `Luiz Duarte` | `568970` |

---

## Problema, público e escopo

**Problema.** Cidadãos encontram informações dispersas e linguagem difícil sobre documentos, serviços e direitos.

**Público.** Pessoas que buscam orientação inicial sobre rotinas administrativas e comunitárias (estudantes, famílias, usuários de serviços públicos).

**Temas da base.**

1. `documentacao` — CPF, CIN/RG, título de eleitor, CNH, CTPS digital, conta gov.br  
2. `servicos_publicos` — CadÚnico, Bolsa Família, INSS, Cartão SUS, Consumidor.gov.br  
3. `orientacao_comunitaria` — Procon, Disque 100, Ligue 180, CRAS, educação/EJA, inclusão  

---

## Como executar

Na raiz do repositório (Python 3.10+; apenas biblioteca padrão):

```bash
python src/sistema.py
# ou
python3 src/sistema.py
```

Bateria de testes e métricas:

```bash
python3 src/sistema.py --testes
```

Comparação qualitativa dos modelos A e B:

```bash
python3 src/sistema.py --comparar
```

---

## Organização da base e estratégia de busca

- Arquivo: [`data/base.json`](data/base.json) (17 orientações).  
- Campos: `id`, `tema`, `subtema`, `palavras_chave`, `sinonimos`, `pergunta`, `orientacao`, `referencia`, `data_verificacao`.  
- Estruturas: **listas** de registros; **dicionários** por `id` e por `tema`/`subtema`.  
- **Busca:** normalização, stopwords, score por palavras-chave/sinônimos (+ pergunta). Várias correspondências próximas → **ambiguidade** com escolha.  
- **Grafo de navegação:** temas + subtemas (`grafo_navegacao`); **Dijkstra** calcula caminhos multi-hop (ex.: `cpf > govbr > inss`).  
- Novos registros no JSON não exigem reescrever as regras centrais.

---

## Regras de resposta e prompts

| Modelo | Conteúdo |
|--------|----------|
| **A (padrão)** | Papel do assistente + orientação + fonte + data + aviso de não oficialidade |
| **B** | Orientação + fonte (mais curto) |

Comparação qualitativa (rubrica 0–2: clareza, citação, aviso, completude) em [`data/comparacao_modelos.json`](data/comparacao_modelos.json): **A = 8,0/8** vs **B = 6,2/8**. A recuperação do *id* é igual nos dois; o Modelo A vence pela responsabilidade da resposta.

**Limitações tratadas:** entrada vazia, só símbolos, opção inexistente, sem correspondência, ambiguidade.

**Lógica (De Morgan — Fase 5):** válida ⇔ não vazia ∧ tem alfanumérico; inválida ⇔ vazia ∨ sem alfanumérico.

---

## Testes, indicadores e resultados

- Casos: [`data/perguntas_teste.json`](data/perguntas_teste.json) (12+ e limites).  
- Saída enriquecida: [`data/resultados_testes.json`](data/resultados_testes.json) (esperado, obtido, acerto, tempo).

Indicadores da última execução (`--testes` / `--comparar`):

- **Taxa de acerto:** 100% (16/16) com critérios **estritos** (ambiguidade exige ≥2 candidatos ou status ambíguo)  
- **Tempo médio:** ~1,5 ms  
- T16 (`carteira de identidade` + `carteira de trabalho`) resulta em **status=ambiguo** com candidatos DOC-005, DOC-002, DOC-004  

Interpretação: a base é finita e alinhada aos testes; em linguagem coloquial real a taxa cairia. Melhorias: mais sinônimos regionais, teste com usuário externo.

---

## Exemplo completo (Modelo A)

**Pergunta:** `Como consultar meu CPF?`

```text
Sou o Citizen Assist AI, um assistente introdutório de orientação cidadã.
Não substituo canais oficiais de órgãos públicos.

Sobre: Como consultar ou regularizar o CPF?
Orientação: A consulta da situação cadastral do CPF pode ser feita no site da Receita Federal. ...
Fonte consultada: https://www.gov.br/receitafederal/pt-br/assuntos/cadastros/cpf
Data de verificação: 2026-11-15
[Confirmação] Esta orientação pode exigir requisitos atualizados. ...

Sempre confirme as informações no site oficial antes de tomar decisões.
```

**Entrada vazia / `???`:** mensagem de erro, sem inventar conteúdo.  
**Fora de tema:** aviso de ausência + temas/sugestões.  
**Ambiguidade:** lista numerada de candidatos para o usuário escolher.

---

## Arquivos da entrega vs material de estudo

**Entrega (corrigir/avaliar):**

```text
README.md
src/sistema.py
data/base.json
data/perguntas_teste.json
data/resultados_testes.json
data/comparacao_modelos.json
docs/relatorio.md
```

---

## Cuidados (clareza, acessibilidade, privacidade)

- Linguagem acentuada (UTF-8); avisos de limitação visíveis.  
- Não solicita dados pessoais desnecessários.  
- Não promete integração com órgãos públicos.  
- Fontes e datas de verificação nas respostas.
