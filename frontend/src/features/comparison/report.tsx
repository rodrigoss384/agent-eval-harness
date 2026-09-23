import { useQuery } from '@tanstack/react-query'
import { Check, ChevronDown, CircleAlert, FileText, ScanLine } from 'lucide-react'
import { useState } from 'react'
import type { ReactNode } from 'react'

import { getBenchmarkSummary, type Benchmark, type BenchmarkSummary, type Evaluation, type MethodStats } from './contracts'
import { inputClass, money, number, Panel, percent, Stat, statusLabel } from './ui'

const names = { llm_as_judge: 'LLM como juiz', decision_model: 'Jev' }
const methods = ['llm_as_judge', 'decision_model'] as const
const cell = 'border-b border-border px-4 py-3 text-left align-top text-sm'

function Verdict({ result }: { result: Evaluation | undefined }) {
  if (!result) return <span className="text-muted">Ainda não avaliado</span>
  return <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${result.passed === true ? 'bg-success/10 text-success' : result.passed === false ? 'bg-danger/10 text-danger' : 'bg-warning/10 text-warning'}`}>
    {result.passed === true ? <Check size={14} /> : <CircleAlert size={14} />}{result.passed === true ? 'Aprovado' : result.passed === false ? 'Reprovado' : 'Sem veredito'}
  </span>
}

function EvaluationCard({ evaluation, method }: { evaluation?: Evaluation; method: typeof methods[number] }) {
  const m = evaluation?.metrics
  return <Panel className={method === 'decision_model' ? 'border-accent/40' : ''}>
    <div className="flex flex-wrap items-center justify-between gap-3"><h4 className="text-lg font-semibold">{names[method]}</h4><Verdict result={evaluation} /></div>
    <p className="mt-2 break-all text-xs text-muted">{evaluation?.judge_model ?? 'Modelo não registrado'} · {evaluation?.judge_provider ?? 'Provider não registrado'}</p>
    <div className="mt-5 grid grid-cols-2 gap-3"><div><p className="text-xs text-secondary">{method === 'decision_model' ? 'Probabilidade' : 'Nota da rubrica'}</p><p className="mt-1 text-3xl font-semibold tabular-nums">{evaluation?.score == null ? '—' : evaluation.score.toPrecision(6)}</p></div><div><p className="text-xs text-secondary">Limiar do caso</p><p className="mt-1 text-3xl font-semibold tabular-nums">{evaluation?.threshold ?? '—'}</p></div></div>
    <dl className="mt-5 grid grid-cols-2 gap-4 border-y border-border py-4 text-sm">
      <div><dt className="text-xs text-muted">Tempo da chamada</dt><dd className="mt-1 font-semibold">{m?.latency_ms == null ? 'Não registrado' : `${m.latency_ms} ms`}</dd></div>
      <div><dt className="text-xs text-muted">Espera por concorrência</dt><dd className="mt-1">{m?.queue_ms == null ? 'Não registrada' : `${m.queue_ms} ms`}</dd></div>
      <div><dt className="text-xs text-muted">Tokens · entrada / saída</dt><dd className="mt-1">{number(m?.input_tokens)} / {number(m?.output_tokens)}</dd></div>
      <div><dt className="text-xs text-muted">Custo {m?.cost_status === 'estimated' ? 'estimado' : m?.cost_status === 'reported' ? 'informado' : 'indisponível'}</dt><dd className="mt-1 font-semibold">{money(m?.cost_usd)}</dd></div>
    </dl>
    <h5 className="mt-5 flex items-center gap-2 text-sm font-semibold"><FileText size={15} />{method === 'decision_model' ? 'Sem racional textual' : 'Justificativa gerada pelo LLM'}</h5>
    <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-6 text-secondary">{evaluation?.reason ?? 'Não há resposta deste avaliador.'}</p>
    {method === 'llm_as_judge' && <p className="mt-2 text-xs text-muted">A justificativa pode estar errada; não é prova independente de correção.</p>}
    {evaluation && <details className="mt-4"><summary className="cursor-pointer text-sm font-medium text-accent">Evidências e rastreabilidade</summary><dl className="mt-3 space-y-2 break-words text-xs text-secondary"><div>{evaluation.request_id?.startsWith('lc_run') ? 'ID local do cliente (ID do provider não registrado)' : 'ID da resposta do provider'}: {evaluation.request_id ?? 'Não informado'}</div><div>Protocolo: {evaluation.protocol_version ?? 'Não registrado'}</div><div>Provider de execução: {evaluation.upstream_provider ?? evaluation.judge_provider}</div><div>Cache de entrada: {number(m?.cached_input_tokens)} tokens</div><div>Fórmula: {m?.cost_formula ?? 'Não se aplica / não informada'}</div><div>Catálogo: {m?.pricing_version ?? 'Não se aplica'}</div></dl><pre className="mt-3 max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-canvas p-3 text-xs">{JSON.stringify(evaluation.evidence, null, 2)}</pre></details>}
  </Panel>
}

export function BenchmarkReport({ benchmark, summary }: { benchmark: Benchmark; summary: BenchmarkSummary }) {
  const [sampleId, setSampleId] = useState(benchmark.samples[0]?.id ?? '')
  const [onlyDisagreements, setOnlyDisagreements] = useState(false)
  const [threshold, setThreshold] = useState(.8)
  const [sensitivity, setSensitivity] = useState(false)
  const exploratory = useQuery({ queryKey: ['sensitivity', benchmark.benchmark_id, threshold, benchmark.updated_at],
    queryFn: () => getBenchmarkSummary(benchmark.recorded ? 'example' : benchmark.benchmark_id, threshold), enabled: sensitivity })
  const disagreementIds = new Set(benchmark.runs.filter(r => {
    const a = r.evaluations.find(e => e.method === 'llm_as_judge')?.passed
    const b = r.evaluations.find(e => e.method === 'decision_model')?.passed
    return a != null && b != null && a !== b
  }).map(r => r.sample_id))
  const samples = benchmark.samples.filter(s => !onlyDisagreements || disagreementIds.has(s.id))
  const selected = samples.find(s => s.id === sampleId) ?? samples[0]
  const runs = benchmark.runs.filter(r => r.sample_id === selected?.id)
  const llm = summary.methods.llm_as_judge
  const jev = summary.methods.decision_model
  const rows: [string, (s: MethodStats) => ReactNode][] = [
    ['Acerto contra o rótulo de referência', s => percent(s.accuracy)],
    ['Precisão · aprovações que estavam corretas', s => percent(s.precision)],
    ['Recall · respostas corretas aprovadas', s => percent(s.recall)],
    ['F1 · equilíbrio entre precisão e recall', s => percent(s.f1)],
    ['Corretas aprovadas / incorretas reprovadas', s => `${number(s.confusion.tp)} / ${number(s.confusion.tn)}`],
    ['Falsos positivos / falsos negativos', s => `${number(s.confusion.fp)} / ${number(s.confusion.fn)}`],
    ['Candidatos com algum resultado / total', s => `${s.distinct_candidates} / ${s.expected_candidates}`],
    ['Candidatos com três julgamentos válidos', s => s.complete_candidates],
    ['Candidatos com mudança de veredito', s => s.unstable_candidates],
    ['Dispersão média dos scores (desvio padrão)', s => number(s.mean_score_stddev)],
    ['Tempo mediano / p95 da chamada', s => `${number(s.latency_p50_ms)} / ${number(s.latency_p95_ms)} ms`],
    ['Chamadas com erro ou indisponibilidade', s => s.errors ?? 0],
    ['Timeouts registrados', s => s.timeouts ?? 0],
    ['Tokens de entrada / saída conhecidos', s => `${number(s.input_tokens)} / ${number(s.output_tokens)}`],
    ['Chamadas sem tokens informados', s => s.calls_without_tokens ?? 0],
    ['Custo informado pelo provider', s => money(s.reported_cost_usd)],
    ['Custo estimado pelo catálogo', s => money(s.estimated_cost_usd)],
    ['Chamadas sem custo conhecido', s => s.calls_without_cost ?? 0],
  ]
  return <div className="space-y-8">
    <div className="flex flex-wrap items-center justify-between gap-3 text-sm"><p className="rounded-full border border-border bg-panel px-3 py-1.5 font-medium">{benchmark.recorded ? 'Evidência real registrada · não executada agora' : statusLabel(benchmark.status)}</p><p className="text-secondary">{new Date(benchmark.created_at).toLocaleString('pt-BR')} · {benchmark.protocol_version}</p></div>
    {benchmark.error && <p role="alert" className="rounded-xl border border-warning/30 bg-warning/5 p-4 text-sm text-warning">{benchmark.error}</p>}
    <section aria-label="Resumo da comparação" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <Stat label="Respostas distintas" value={summary.distinct_candidates} note={`${summary.distinct_cases} casos · três repetições por resposta`} />
      <Stat label="Concordância entre os juízes" value={percent(summary.comparison.agreement_rate)} note={`${summary.comparison.agreements} de ${summary.comparison.paired_trials} pares válidos; concordância não prova acerto`} />
      <Stat label="Divergências" value={summary.comparison.disagreements} note={`${summary.comparison.unpaired_trials} tentativas sem o par completo`} />
      <Stat label="Consumo contabilizado" value={`US$ ${benchmark.accounted_usd.toFixed(5)}`} note={`${benchmark.calls.length} chamadas · ${summary.uncertain_calls} com reserva incerta · inclui estimativas`} />
    </section>
    <Panel>
      <div className="flex flex-wrap items-start justify-between gap-4"><div><p className="text-xs font-semibold uppercase tracking-wider text-accent">01 / Visão geral</p><h2 className="mt-2 text-2xl font-semibold tracking-tight">O que as medições mostram</h2><p className="mt-3 max-w-3xl text-sm leading-6 text-secondary">Qualidade é medida contra os rótulos preparados antes do teste. Cada resposta tem o mesmo peso, mesmo com três repetições. Custos e latências pertencem aos serviços identificados abaixo.</p></div><ScanLine className="text-accent" size={26} /></div>
      <div className="mt-6 overflow-x-auto"><table className="w-full min-w-[540px]"><caption className="sr-only">Métricas individuais dos juízes</caption><thead><tr><th className={cell}>Métrica</th><th className={`${cell} w-[25%]`}>LLM como juiz<p className="mt-1 text-xs font-normal text-secondary">GPT-4.1 mini · OpenAI</p></th><th className={`${cell} w-[25%] bg-accent/5 text-accent`}>Jev<p className="mt-1 text-xs font-normal text-secondary">Jev 1.13 · OpenRouter</p></th></tr></thead><tbody>{rows.map(([label, display]) => <tr key={label}><th className={`${cell} font-normal text-secondary`}>{label}</th><td className={`${cell} font-medium tabular-nums`}>{llm ? display(llm) : '—'}</td><td className={`${cell} bg-accent/5 font-medium tabular-nums`}>{jev ? display(jev) : '—'}</td></tr>)}</tbody></table></div>
      <p className="mt-4 text-xs leading-6 text-muted">{summary.weighting} A matriz de confusão tem contagens ponderadas, que podem ser fracionárias. Métricas sem denominador são exibidas como indisponíveis.</p>
    </Panel>
    <Panel>
      <p className="text-xs font-semibold uppercase tracking-wider text-accent">02 / Resposta por resposta</p><h2 className="mt-2 text-2xl font-semibold tracking-tight">Inspecione os dois vereditos</h2>
      <label className="mt-5 inline-flex items-center gap-2 text-sm"><input type="checkbox" checked={onlyDisagreements} onChange={e => setOnlyDisagreements(e.target.checked)} className="size-4 accent-accent" />Mostrar somente respostas com divergência ({disagreementIds.size})</label>
      <label className="mt-4 block text-sm font-medium">Resposta avaliada<select className={inputClass} value={selected?.id} onChange={e => setSampleId(e.target.value)}>{samples.map(s => <option key={s.id} value={s.id}>{s.expected_passed ? 'Correta' : 'Incorreta'} · {s.case.input}</option>)}</select></label>
      {onlyDisagreements && !samples.length ? <p className="mt-4 text-sm text-secondary">Nenhuma divergência observada nos pares disponíveis.</p> : selected && <>
        <div className="mt-5 grid gap-4 lg:grid-cols-2"><div className="rounded-xl bg-canvas p-4"><p className="text-xs font-semibold text-muted">PERGUNTA E CRITÉRIO</p><h3 className="mt-2 font-semibold">{selected.case.input}</h3><p className="mt-2 text-sm leading-6 text-secondary">{selected.case.correctness_definition}</p><p className="mt-3 text-xs text-muted">{selected.case.category} · {selected.case.difficulty} · limiar {selected.case.threshold}</p></div><div className="rounded-xl bg-canvas p-4"><p className="text-xs font-semibold text-muted">RESPOSTA FORNECIDA · NÃO GERADA AGORA</p><p className="mt-2 whitespace-pre-wrap break-words text-sm leading-6">{selected.output}</p><p className="mt-3 text-xs font-semibold text-secondary">Rótulo de referência: {selected.expected_passed ? 'correta' : 'incorreta'}</p><p className="mt-1 text-xs leading-5 text-muted">{selected.label_reason} Este rótulo não foi enviado aos juízes.</p></div></div>
        <details className="mt-4 rounded-lg border border-border p-4"><summary className="cursor-pointer text-sm font-medium">Ver ground truth, fontes e rubrica</summary><p className="mt-3 text-sm leading-6">{selected.case.expected_output}</p><ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-secondary">{selected.case.rubric.map(r => <li key={r}>{r}</li>)}</ul>{selected.case.reference_context.map(c => <p className="mt-2 text-sm leading-6 text-secondary" key={c.id}>[{c.id}] {c.text}</p>)}{selected.tool_calls.length > 0 && <pre className="mt-3 overflow-auto text-xs">{JSON.stringify(selected.tool_calls, null, 2)}</pre>}</details>
        {[1, 2, 3].map(trial => <details key={`${selected.id}-${trial}`} open={trial === 1} className="mt-5"><summary className="flex cursor-pointer items-center gap-2 py-2 text-sm font-semibold"><ChevronDown size={16} />Tentativa {trial} · mesma resposta para os dois juízes</summary><div className="mt-3 grid items-start gap-4 lg:grid-cols-2">{methods.map(method => <EvaluationCard key={method} method={method} evaluation={runs.find(r => r.trial_index === trial)?.evaluations.find(e => e.method === method)} />)}</div></details>)}
      </>}
    </Panel>
    <div className="grid items-start gap-5 xl:grid-cols-2">
      <Panel><p className="text-xs font-semibold uppercase tracking-wider text-accent">03 / Probabilidade</p><h2 className="mt-2 text-xl font-semibold">O número acompanha os acertos?</h2><p className="mt-3 text-sm leading-6 text-secondary">Brier do Jev: <strong>{jev?.brier_score == null ? 'não disponível' : jev.brier_score.toFixed(6)}</strong>. Menor é melhor. A curva abaixo agrupa a probabilidade média de cada resposta; não certifica calibração fora desta amostra.</p>
        <svg viewBox="0 0 300 230" role="img" aria-label="Confiabilidade do Jev: eixo horizontal probabilidade média, vertical frequência observada" className="mt-5 w-full max-w-lg"><path d="M40 15V195H280" fill="none" stroke="currentColor" className="text-border" /><path d="M40 195L280 15" stroke="currentColor" strokeDasharray="5 5" className="text-muted" /><text x="42" y="225" fontSize="10" fill="currentColor">0 · probabilidade média → 1</text><text x="3" y="17" fontSize="10" fill="currentColor">100%</text><text x="9" y="195" fontSize="10" fill="currentColor">0%</text>{jev?.reliability.filter(b => b.count > 0).map(b => <circle key={b.lower} cx={40 + (b.mean_probability ?? 0) * 240} cy={195 - (b.observed_frequency ?? 0) * 180} r={5 + Math.sqrt(b.count)} fill="currentColor" fillOpacity=".7" className="text-accent"><title>{b.count} respostas; probabilidade {percent(b.mean_probability)}; frequência {percent(b.observed_frequency)}</title></circle>)}</svg>
        <div className="overflow-x-auto"><table className="w-full text-xs"><caption className="sr-only">Dados da curva de confiabilidade</caption><thead><tr><th className="p-2 text-left">Faixa</th><th className="p-2">Respostas</th><th className="p-2">Probabilidade</th><th className="p-2">Frequência</th></tr></thead><tbody>{jev?.reliability.map(b => <tr key={b.lower}><td className="p-2">{b.lower.toFixed(1)}–{b.upper.toFixed(1)}</td><td className="p-2 text-center">{b.count}</td><td className="p-2 text-center">{b.count ? percent(b.mean_probability) : '—'}</td><td className="p-2 text-center">{b.count ? percent(b.observed_frequency) : '—'}</td></tr>)}</tbody></table></div><p className="mt-3 text-xs leading-5 text-muted">O score do LLM é uma nota da rubrica. Aplicar Brier a essa nota como se fosse uma probabilidade seria uma comparação inadequada.</p>
      </Panel>
      <Panel><p className="text-xs font-semibold uppercase tracking-wider text-accent">04 / Sensibilidade</p><h2 className="mt-2 text-xl font-semibold">E se o limiar fosse diferente?</h2><p className="mt-3 text-sm leading-6 text-secondary">O resultado oficial usa o limiar de cada caso. Nove dos 24 casos exigem 1,0: uma probabilidade de 0,999 reprova. Explore outros cortes sem chamadas adicionais.</p><label className="mt-5 flex items-center gap-2 text-sm font-medium"><input className="size-4 accent-accent" type="checkbox" checked={sensitivity} onChange={e => setSensitivity(e.target.checked)} />Ativar análise exploratória</label>{sensitivity && <><label className="mt-5 block text-sm">Limiar exploratório: <strong>{threshold.toFixed(2)}</strong><input type="range" min="0" max="1" step=".01" value={threshold} onChange={e => setThreshold(Number(e.target.value))} className="mt-3 w-full accent-accent" /></label><div className="mt-5 grid grid-cols-2 gap-3">{methods.map(m => <Stat key={m} label={`${names[m]} · acerto exploratório`} value={percent(exploratory.data?.methods[m]?.accuracy)} />)}</div>{exploratory.isFetching && <p role="status" className="mt-3 text-xs">Recalculando apenas os dados salvos…</p>}{exploratory.error && <p role="alert" className="mt-3 text-sm text-danger">{exploratory.error.message}</p>}</>}<p className="mt-5 rounded-lg bg-warning/5 p-3 text-xs leading-6 text-warning">Esta análise usa score ≥ corte para os dois métodos. Não muda os vereditos registrados e não torna suas escalas equivalentes.</p></Panel>
    </div>
    <Panel><p className="text-xs font-semibold uppercase tracking-wider text-accent">05 / Capacidades e limites</p><h2 className="mt-2 text-2xl font-semibold">O que está sendo comparado</h2><div className="mt-5 overflow-x-auto"><table className="w-full min-w-[560px]"><thead><tr><th className={cell}>Capacidade</th><th className={cell}>LLM como juiz</th><th className={cell}>Jev</th></tr></thead><tbody>{[
      ['Saída integrada', 'Texto JSON: score, passed, reason e evidence', 'Resposta tipada noul: probabilidade entre 0 e 1'],
      ['Explicação', 'Racional gerado, sujeito a erro', 'Sem racional textual; tokens de saída podem constar no usage da API'],
      ['Escala', 'Nota de atendimento à rubrica', 'Probabilidade da resposta à pergunta binária'],
      ['Entrada deste protocolo', 'Texto, contexto e traces de ferramentas', 'O mesmo texto, contexto e traces'],
      ['Outros formatos', 'Capacidades gerais do modelo não exercitadas aqui', 'choice e score documentados na API; não integrados nesta versão'],
      ['Calibração', 'Não se assume que a nota seja calibrada', 'Avaliação descritiva nesta amostra; sem certificação geral'],
      ['Viés e resistência a instruções maliciosas', 'Não medidos por este benchmark', 'Não medidos por este benchmark'],
      ['Operação', 'OpenAI direta · sem retry automático', 'OpenRouter Decisions · sem retry automático'],
      ['Uso a investigar', 'Auditoria que demanda justificativa verificável', 'Decisões em volume, após validar o domínio e o limiar'],
    ].map(([a, b, c]) => <tr key={a}><th className={`${cell} font-normal text-secondary`}>{a}</th><td className={cell}>{b}</td><td className={cell}>{c}</td></tr>)}</tbody></table></div></Panel>
    <Panel><p className="text-xs font-semibold uppercase tracking-wider text-accent">06 / Metodologia aberta</p><h2 className="mt-2 text-2xl font-semibold">Como reproduzir e interpretar</h2><p className="mt-3 text-sm leading-7 text-secondary">{summary.distinct_cases} casos sintéticos, uma resposta correta e uma incorreta por caso. Três repetições com entradas fixas, ordem alternada dos juízes e chamadas sequenciais. Os rótulos e suas justificativas ficam fora dos prompts. O GPT-4.1 mini usa temperatura 0 e até 800 tokens de saída; Jev recebe uma pergunta noul. Não há geração de agente neste protocolo.</p><ul className="mt-4 list-disc space-y-2 pl-5 text-sm leading-6 text-secondary">{summary.limitations.map(l => <li key={l}>{l}</li>)}</ul><dl className="mt-5 grid gap-4 border-t border-border pt-5 text-xs sm:grid-cols-2"><div><dt className="text-muted">Dataset / protocolo</dt><dd className="mt-1">{benchmark.dataset_version} / {benchmark.protocol_version}</dd></div><div><dt className="text-muted">Execução</dt><dd className="mt-1">{benchmark.benchmark_id}</dd></div><div className="sm:col-span-2"><dt className="text-muted">Checksum dos casos e candidatos</dt><dd className="mt-1 break-all font-mono">{benchmark.dataset_checksum}</dd></div></dl><details className="mt-5"><summary className="cursor-pointer text-sm font-semibold text-accent">Configuração e catálogo usados</summary><pre className="mt-3 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-canvas p-4 text-xs">{JSON.stringify(benchmark.configuration, null, 2)}</pre></details><details className="mt-5"><summary className="cursor-pointer text-sm font-semibold text-accent">Registro completo de chamadas e reservas</summary><div className="mt-3 max-h-80 overflow-auto"><table className="w-full min-w-[600px] text-xs"><thead><tr>{['Resposta / tentativa', 'Método', 'Estado', 'Reserva', 'Contabilizado', 'Origem'].map(t => <th key={t} className="p-2 text-left">{t}</th>)}</tr></thead><tbody>{benchmark.calls.map((c, i) => <tr key={i}><td className="p-2">{c.sample_id} / {c.trial_index}</td><td className="p-2">{c.method}</td><td className="p-2">{c.status}</td><td className="p-2">{money(c.reserved_usd)}</td><td className="p-2">{money(c.accounted_usd)}</td><td className="p-2">{c.accounting}</td></tr>)}</tbody></table></div></details></Panel>
  </div>
}
