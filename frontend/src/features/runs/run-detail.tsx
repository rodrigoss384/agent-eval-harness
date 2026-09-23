import * as Collapsible from '@radix-ui/react-collapsible'
import { ChevronDown, Clock3, Coins, Hash, MessageSquareQuote, CheckCircle2, XCircle, AlertCircle, Bot, FileInput } from 'lucide-react'

import type { RunVerdict } from './schemas'
import { StatusPill } from './status-pill'

const methodLabels = {
  deterministic_match: 'Validação Exata (Match Determinístico)',
  programmatic_check: 'Validação por Regra (Check Programático)',
  llm_as_judge: 'LLM como juiz',
  decision_model: 'Jev · modelo de decisão',
}

const evaluationLabels = {
  passed: 'Aprovado',
  failed: 'Reprovado',
  observed: 'Apenas Observado',
  unavailable: 'Indisponível',
  error: 'Erro de Execução',
}

function Metric({ label, sublabel, value, icon: Icon }: { label: string; sublabel?: string; value: string; icon: typeof Clock3 }) {
  return (
    <div className="rounded-lg border border-border bg-canvas px-3 py-2.5">
      <span className="flex items-center gap-1.5 text-xs text-muted">
        <Icon aria-hidden="true" className="size-3.5" />
        {label}
      </span>
      <span className="mt-1 block text-sm font-medium text-primary">{value}</span>
      {sublabel ? <span className="mt-0.5 block text-[10px] text-muted">{sublabel}</span> : null}
    </div>
  )
}

function getVerdictBanner(verdict: RunVerdict['final_verdict']) {
  switch (verdict) {
    case 'pass':
      return { bg: 'bg-success/10', border: 'border-success/30', text: 'text-success', icon: CheckCircle2, title: 'Sucesso: a resposta atingiu o objetivo esperado' }
    case 'fail':
      return { bg: 'bg-danger/10', border: 'border-danger/30', text: 'text-danger', icon: XCircle, title: 'Falha: a resposta não atendeu aos critérios' }
    default:
      return { bg: 'bg-warning/10', border: 'border-warning/30', text: 'text-warning', icon: AlertCircle, title: 'Inconclusivo: Não foi possível determinar o resultado' }
  }
}

export function RunDetail({ verdict }: { verdict: RunVerdict }) {
  const banner = getVerdictBanner(verdict.final_verdict)
  const failedEvaluation = verdict.evaluations.find((evaluation) => evaluation.passed === false || evaluation.status === 'failed')
  const mainEval = verdict.final_verdict === 'fail'
    ? failedEvaluation ?? verdict.evaluations[0]
    : verdict.evaluations.find((evaluation) => evaluation.method === 'llm_as_judge') ?? verdict.evaluations[0]
  const normative = verdict.evaluations.filter((evaluation) => evaluation.passed !== null && evaluation.passed !== undefined)
  const methodsDisagree = normative.some((evaluation) => evaluation.passed === true) && normative.some((evaluation) => evaluation.passed === false)
  const suppliedTrace = verdict.candidate_origin === 'supplied_trace'

  return (
    <article className="rounded-xl border border-border bg-panel">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-3">
        <div>
          <p className="font-mono text-xs text-muted">Run ID: {verdict.run_id}</p>
          <h2 className="text-sm font-semibold tracking-[-0.02em] text-primary">Cenário: {verdict.case_id} (Tentativa {verdict.trial_index ?? 'manual'})</h2>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-canvas px-2.5 py-1 text-xs text-secondary">
            {suppliedTrace ? <FileInput aria-hidden="true" className="size-3.5" /> : <Bot aria-hidden="true" className="size-3.5" />}
            {suppliedTrace ? 'Trace fornecido · não gerado por IA' : 'Resposta gerada por modelo real'}
          </span>
          <StatusPill verdict={verdict.final_verdict} />
        </div>
      </div>

      <header className="p-5 sm:p-6">
        <div className={`rounded-lg border p-4 ${banner.bg} ${banner.border}`}>
          <div className={`flex items-center gap-2 font-semibold ${banner.text}`}>
            <banner.icon aria-hidden="true" className="size-5" />
            <h3 className="text-base">{banner.title}</h3>
          </div>
          <p className="mt-2 text-sm leading-6 text-primary">{verdict.final_verdict === 'fail' ? 'Basta um critério normativo falhar para que o resultado final seja reprovado.' : verdict.final_verdict === 'pass' ? 'Todos os critérios normativos disponíveis foram atendidos.' : 'Não havia evidência suficiente para emitir aprovação ou reprovação.'}</p>
        </div>

        {methodsDisagree ? <div className="mt-4 rounded-lg border border-warning/30 bg-warning/8 p-4 text-sm text-warning"><strong>Os métodos discordaram.</strong> O resultado final segue os critérios normativos: qualquer falha normativa reprova a tentativa. Abra as avaliações detalhadas para comparar cada método.</div> : null}

        <div className="mt-5 grid gap-3 sm:grid-cols-2">
          <div className="rounded-lg border border-border bg-canvas p-4"><p className="text-xs font-semibold uppercase tracking-wider text-muted">1. O que foi testado</p><p className="mt-2 text-sm leading-6 text-secondary">{verdict.agent_input}</p></div>
          <div className="rounded-lg border border-border bg-canvas p-4"><p className="text-xs font-semibold uppercase tracking-wider text-muted">2. Qual era a regra</p><p className="mt-2 text-sm leading-6 text-secondary">{mainEval?.correctness_definition ?? 'Nenhuma regra disponível.'}</p></div>
          <div className="rounded-lg border border-border bg-canvas p-4"><p className="text-xs font-semibold uppercase tracking-wider text-muted">3. O que aconteceu</p><p className="mt-2 break-words text-sm leading-6 text-secondary">{mainEval?.actual ?? (verdict.agent_output || 'Nenhuma resposta textual; consulte as ferramentas utilizadas.')}</p></div>
          <div className="rounded-lg border border-border bg-canvas p-4"><p className="text-xs font-semibold uppercase tracking-wider text-muted">4. Por que passou ou falhou</p><p className="mt-2 text-sm leading-6 text-primary">{mainEval?.reason ?? 'Justificativa não disponível.'}</p></div>
        </div>

        <div className="mt-6">
          <p className="text-xs font-semibold uppercase tracking-wider text-muted">{suppliedTrace ? 'Resposta fornecida para avaliação' : 'Resposta gerada pelo agente'}</p>
          <div className="mt-2 whitespace-pre-wrap rounded-lg border border-border bg-canvas p-4 text-sm leading-6 text-primary">
            {verdict.agent_output || <span className="text-muted">Sem resposta textual.</span>}
          </div>
        </div>

        {verdict.tool_calls.length ? (
          <details className="mt-4 rounded-lg border border-accent/20 bg-accent/5 px-4 py-3">
            <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wider text-accent focus-visible:outline-2 focus-visible:outline-accent">
              Ferramentas utilizadas · detalhes técnicos
            </summary>
            <pre className="mt-3 overflow-auto text-xs text-secondary">
              {JSON.stringify(verdict.tool_calls, null, 2)}
            </pre>
          </details>
        ) : null}
      </header>

      {verdict.retrieved_context?.length ? (
        <details className="border-t border-border px-5 py-4">
          <summary className="cursor-pointer text-sm font-medium text-secondary focus-visible:outline-2 focus-visible:outline-accent">
            Contexto recuperado da base de conhecimento
          </summary>
          <ol className="mt-3 space-y-2">
            {verdict.retrieved_context.map((chunk, index) => (
              <li key={String(chunk.id)} className="rounded-lg bg-canvas p-3 text-xs leading-5 text-secondary">
                <span className="font-mono text-accent">#{index + 1} [{String(chunk.id)}] · score (relevância) {Number(chunk.score).toFixed(4)}</span>
                <p className="mt-1">{String(chunk.text)}</p>
              </li>
            ))}
          </ol>
        </details>
      ) : null}

      <div className="grid grid-cols-1 gap-2 border-y border-border p-4 sm:grid-cols-3 sm:p-5">
        <Metric
          label="Latência"
          sublabel="(Tempo de Resposta)"
          value={verdict.metrics.latency_ms === null ? 'Não informada' : `${verdict.metrics.latency_ms} ms`}
          icon={Clock3}
        />
        <Metric
          label="Tokens"
          sublabel="(Volume Processado)"
          value={verdict.metrics.total_tokens === null ? 'Não informados' : String(verdict.metrics.total_tokens)}
          icon={Hash}
        />
        <Metric
          label="Custo"
          sublabel="(Gasto da Chamada)"
          value={verdict.metrics.cost_usd === null ? 'Não informado pelo provider' : `US$ ${verdict.metrics.cost_usd.toFixed(6)}${verdict.metrics.cost_status === 'estimated' ? ' estimado' : ''}`}
          icon={Coins}
        />
      </div>

      <details className="p-4 sm:p-5 group">
        <summary className="flex cursor-pointer items-center gap-2 text-sm font-semibold text-primary focus-visible:outline-2 focus-visible:outline-accent">
          <MessageSquareQuote aria-hidden="true" className="size-4 text-muted" />
          Como cada método avaliou esta resposta
          <ChevronDown aria-hidden="true" className="size-4 text-muted transition-transform group-open:rotate-180" />
        </summary>
        <div className="mt-4 space-y-2">
          {verdict.evaluations.map((evaluation) => (
            <Collapsible.Root key={evaluation.method} className="rounded-lg border border-border bg-canvas">
              <Collapsible.Trigger className="group/col flex w-full items-center justify-between gap-4 px-4 py-3 text-left focus-visible:outline-2 focus-visible:outline-accent">
                <span>
                  <span className="block text-sm font-medium text-primary">{methodLabels[evaluation.method] ?? evaluation.method}</span>
                  <span className="mt-0.5 block text-xs text-muted">{evaluationLabels[evaluation.status] ?? evaluation.status}</span>
                </span>
                <ChevronDown aria-hidden="true" className="size-4 text-muted transition-transform group-data-[state=open]/col:rotate-180" />
              </Collapsible.Trigger>
              <Collapsible.Content className="border-t border-border px-4 py-4 data-[state=open]:animate-reveal">
                <dl className="grid gap-4 text-sm">
                  <div>
                    <dt className="text-xs font-medium uppercase tracking-[0.1em] text-muted">Definição de Sucesso</dt>
                    <dd className="mt-1.5 leading-6 text-primary">{evaluation.correctness_definition}</dd>
                  </div>
                  {evaluation.score !== null && evaluation.score !== undefined ? (
                    <div className="grid gap-3 sm:grid-cols-2">
                      <div><dt className="text-xs text-muted">{evaluation.score_type === 'probability' ? 'Probabilidade de atender ao critério' : 'Nota de atendimento à rubrica'}</dt><dd className="mt-1 font-mono text-sm text-primary">{evaluation.score.toPrecision(6)}</dd></div>
                      <div><dt className="text-xs text-muted">Nota Mínima (Threshold)</dt><dd className="mt-1 font-mono text-sm text-primary">{evaluation.threshold?.toFixed(2)}</dd></div>
                    </div>
                  ) : null}
                  {evaluation.rubric?.length ? (
                    <div><dt className="text-xs font-medium uppercase tracking-[0.1em] text-muted">Rubrica de Avaliação</dt><dd><ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-secondary">{evaluation.rubric.map((criterion) => <li key={criterion}>{criterion}</li>)}</ul></dd></div>
                  ) : null}
                  <div>
                    <dt className="text-xs font-medium uppercase tracking-[0.1em] text-muted">{evaluation.rationale_available === false ? "Decisão sem racional textual" : "Justificativa Completa"}</dt>
                    <dd className="mt-1.5 leading-6 text-secondary">{evaluation.reason}</dd>
                  </div>
                  <div><dt className="text-xs text-muted">Modelo e provider</dt><dd className="mt-1 break-all">{evaluation.judge_model ?? 'Não se aplica'} · {evaluation.judge_provider ?? 'Não registrado'}</dd></div>
                  {evaluation.metrics ? <div className="grid gap-3 sm:grid-cols-3">
                    <div>Tempo: {evaluation.metrics.latency_ms ?? '—'} ms</div>
                    <div>Tokens: {evaluation.metrics.total_tokens ?? 'Não informados'}</div>
                    <div>Custo: {evaluation.metrics.cost_usd == null ? 'Não informado' : `US$ ${evaluation.metrics.cost_usd.toFixed(8)} (${evaluation.metrics.cost_status === 'reported' ? 'informado' : 'estimado'})`}</div>
                  </div> : <p className="text-xs text-muted">Métricas individuais não registradas nesta versão.</p>}
                  {Object.keys(evaluation.evidence).length > 0 ? <details><summary className="cursor-pointer">Evidências completas</summary><pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap break-words text-xs">{JSON.stringify(evaluation.evidence, null, 2)}</pre></details> : null}
                  {evaluation.expected !== null && evaluation.expected !== undefined ? (
                    <div className="grid gap-3 sm:grid-cols-2">
                      <div>
                        <dt className="text-xs text-muted">Comportamento Esperado</dt>
                        <dd className="mt-1 font-mono text-xs text-primary">{evaluation.expected}</dd>
                      </div>
                      <div>
                        <dt className="text-xs text-muted">Comportamento Observado na IA</dt>
                        <dd className="mt-1 font-mono text-xs text-primary">{evaluation.actual}</dd>
                      </div>
                    </div>
                  ) : null}
                </dl>
              </Collapsible.Content>
            </Collapsible.Root>
          ))}
        </div>
      </details>
    </article>
  )
}
