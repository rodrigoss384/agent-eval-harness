# Protocolo pareado v1

## Amostra congelada

`data/benchmark_candidates_v1.json` contém 48 respostas para os 24 casos originais (oito factuais, oito de recuperação e oito de ferramentas). Cada caso tem uma resposta correta e uma incorreta, com justificativa do rótulo preparada antes da inferência. As incorretas introduzem contradição factual ou argumento de ferramenta errado. Citações obrigatórias estão presentes nas respostas corretas.

A referência semântica é a definição de correto e a rubrica. Os regex determinísticos preexistentes não são o rótulo: podem ter sensibilidade a maiúsculas ou não detectar negação. O protocolo não corrige nem usa esses regex como juiz da comparação.

Cada snapshot guarda os casos completos, candidatos, rótulos, versão e SHA-256 da serialização ordenada dessa amostra. Não basta alterar o arquivo de candidatos para alterar uma execução antiga. Rótulos e justificativas não são enviados aos juízes.

## Chamadas e parâmetros

As chamadas são sequenciais. A ordem alterna por candidato e repetição, balanceada entre os dois serviços. Cada resposta é julgada três vezes sem regeneração. Ambos recebem a mesma string de conteúdo avaliável; instruções específicas de formato são separadas. O estado enviado fica disponível em cada avaliação.

- LLM: `gpt-4.1-mini`, OpenAI direta, temperatura 0, limite de 800 tokens de saída; JSON com score, passed, reason e evidence.
- Jev: `typesafe/jev-1.13`, OpenRouter Decisions, uma pergunta `noul`; probabilidade finita no intervalo fechado [0,1].
- Veredito LLM: booleano do modelo E nota ≥ limiar original.
- Veredito Jev: probabilidade ≥ limiar original.
- Modelos efetivamente retornados, providers, horários, uso e latência são registrados quando informados.
- Sem retry, reparo de JSON, fallback, truncamento silencioso ou retomada automática após reinício.

## Orçamento

O catálogo versionado contém tarifas e fonte. Antes de cada chamada, uma reserva é persistida usando um limite conservador de tokens de entrada (bytes UTF-8 + margem de enquadramento) e o limite de saída. A reserva não usa desconto de cache. Contextos que excedem 32 mil bytes mais margem são recusados.

A reserva é conciliada com custo informado pelo serviço ou estimativa sobre uso informado. Sem informação suficiente, continua reservada. As reservas pendentes contam no teto. Erros contam como chamadas. Uma execução para antes da próxima chamada se o limite de chamadas ou orçamento não comportar a reserva; também para se um custo exceder a reserva ou um juiz apresentar três erros consecutivos.

O teto não é uma garantia de faturamento do provider: tarifas externas podem mudar. O preflight exige tarifas registradas; verifique e atualize o catálogo antes de futuras execuções. A validação desta release usa no máximo 300 chamadas e US$ 2 conjuntamente; diagnósticos, se necessários, ficam fora da amostra e consomem a mesma disponibilidade restante. Não há diagnósticos automáticos.

Reinício marca execuções ativas como interrompidas. Não são retomadas automaticamente. Cancelamento não garante que o provider deixou de cobrar uma chamada já enviada; sua reserva permanece contabilizada.

## Estatísticas

Cada candidato com resultado válido pesa um. Se tiver n julgamentos válidos, cada julgamento pesa 1/n na matriz de confusão. Assim, três repetições não triplicam a amostra. Erros não entram na qualidade; cobertura, resultados ausentes e candidatos com três julgamentos válidos aparecem separadamente.

Precisão = TP/(TP+FP); recall = TP/(TP+FN); F1 = 2TP/(2TP+FP+FN). Denominador zero produz valor indisponível. Concordância considera somente pares completos. Latência mediana e p95 usam o método nearest-rank sobre chamadas com medição disponível. Dispersão considera candidatos com pelo menos duas notas; instabilidade é mudança de veredito observada.

Brier é a média, por candidato, de (p−rótulo)² nas repetições válidas, seguida da média entre candidatos. A curva de confiabilidade usa um ponto por candidato: probabilidade média e rótulo de referência, em cinco faixas. Não se aplica Brier à nota do LLM como se fosse probabilidade.

Sensibilidade reclassifica scores salvos com score ≥ corte para ambos os métodos; é exploratória e não altera o booleano original, o histórico ou a semântica das escalas.

## Limitações

Amostra pequena, sintética, em português e com referências explícitas. Respostas incorretas são controladas, e os argumentos de ferramenta errados são deliberadamente evidentes. Não há execução real de ferramentas. As repetições compartilham caso, candidato e serviços, e não são observações independentes.

Latência inclui rede e providers diferentes. Uma probabilidade alta não prova calibração geral. Racional do LLM não é evidência independente de correção. Não foram medidos vieses, segurança adversarial, uso multimodal ou adequação universal para produção. O uso de limiar 1,0 é preservado por compatibilidade e pode causar falsos negativos no decision model.

Na coleta histórica incluída na 1.1.0, os IDs do LLM são IDs locais do cliente (`lc_run`), explicitamente identificados na interface. O ID da OpenAI não foi preservado nessa coleta. A integração passou a priorizar o ID retornado pelo provider nas execuções seguintes; o histórico não foi reescrito para inventá-lo.

## Evidência da release 1.1.0

Coleta em 23/09/2026, identificador `benchmark_1ead55d890b4`: 288 chamadas, 48 respostas distintas, 24 casos e 144 pares completos. Não foram necessárias chamadas de diagnóstico. Não houve erros nem reservas pendentes.

| Métrica | GPT-4.1 mini / OpenAI | Jev / OpenRouter |
|---|---:|---:|
| Acerto com limiares originais | 100% | 77,08% |
| Verdadeiros positivos / negativos | 24 / 24 | 13 / 24 |
| Falsos positivos / negativos | 0 / 0 | 0 / 11 |
| Latência mediana / p95 | 1.616 / 2.479 ms | 531 / 766 ms |
| Tokens de entrada / saída | 56.883 / 20.950 | 88.674 / 2.880 |
| Custo total | US$ 0,0562732 **estimado** | US$ 0,003724308 **informado** |
| Mudanças de veredito entre repetições | 0 | 0 |

Concordância: 111/144 pares (77,08%), com 33 divergências. Brier do Jev: 0,00726042. Consumo conjunto contabilizado: **US$ 0,059997508**, incluindo a estimativa OpenAI; não equivale a uma fatura consolidada.

Modelos efetivamente retornados: `gpt-4.1-mini-2025-04-14` e `typesafe/jev-1.13-20260917`.
Os nove casos de limiar 1,0 contribuíram com nove dos onze falsos negativos do Jev. Os outros dois vieram de respostas corretas com probabilidade inferior a 0,8. Os resultados não sustentam superioridade geral de um juiz: Jev teve menor custo e latência observados, mas menor acerto com a política original.

O arquivo `data/benchmark_example.json` preserva o snapshot integral e sanitizado da API. A interface o identifica como histórico e permite inspecionar cada par, a referência, a metodologia e os custos. Nenhuma medição foi substituída por valores promocionais.
