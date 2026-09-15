import { Activity, AlertTriangle, CheckCircle2, Clock3, Coins, Hash, Radio, RotateCcw, XCircle } from 'lucide-react'

import type { EvaluationSession, SessionSummary } from './schemas'
import { RunDetail } from './run-detail'

const eventLabels: Record<string, string> = {
  session_started: 'Sessão iniciada',
  case_started: 'Caso carregado',
  retrieval_completed: 'Contexto recuperado',
  generation_started: 'Agente gerando',
  generation_completed: 'Resposta concluída',
  evaluation_started: 'Juiz avaliando',
  evaluation_completed: 'Avaliações concluídas',
  trial_completed: 'Tentativa persistida',
  trial_failed: 'Tentativa inconclusiva',
  case_completed: 'Caso agregado',
  session_completed: 'Sessão concluída',
  session_partial: 'Sessão inconclusiva',
  session_failed: 'Sessão falhou',
  session_cancelled: 'Sessão cancelada',
  session_interrupted: 'Sessão interrompida',
}

function LiveMetric({ label, value, icon: Icon }: { label: string; value: string; icon: typeof Clock3 }) {
  return (
    <div className="rounded-lg border border-border bg-canvas p-3">
      <span className="flex items-center gap-1.5 text-xs text-muted"><Icon aria-hidden="true" className="size-3.5" />{label}</span>
      <strong className="mt-1 block text-sm text-primary">{value}</strong>
    </div>
  )
}

const sessionLabels: Record<EvaluationSession['status'], string> = {
  queued: 'Na fila', running: 'Em andamento', completed: 'Concluída', partial: 'Inconclusiva', failed: 'Erro de execução', cancelled: 'Cancelada', interrupted: 'Interrompida',
}

const caseLabels: Record<string, string> = {
  stable_pass: 'Aprovado nas 3 tentativas', stable_fail: 'Reprovado nas 3 tentativas', unstable: 'Resultados divergentes', inconclusive: 'Evidência insuficiente',
}

function friendlySessionError(error: string) {
  if (/timeout|timed out/i.test(error)) return 'O provider demorou além do limite. As evidências já concluídas foram preservadas.'
  if (/503|unavailable|high demand/i.test(error)) return 'O provider ficou indisponível. As evidências já concluídas foram preservadas.'
  return 'A execução externa não terminou. Consulte o detalhe técnico se precisar diagnosticar o provider.'
}

export function LiveSessionPanel({
  session,
  streamedOutput,
  events,
  reconnecting,
  summary,
  onCancel,
  cancelling,
}: {
  session: EvaluationSession | null
  streamedOutput: string
  events: string[]
  reconnecting: boolean
  summary: SessionSummary | null
  onCancel: (sessionId: string) => void
  cancelling: boolean
}) {
  if (!session) {
    return (
      <section className="grid min-h-80 place-items-center rounded-xl border border-dashed border-border bg-panel/50 p-8 text-center">
        <div>
          <Radio aria-hidden="true" className="mx-auto size-5 text-muted" />
          <h2 className="mt-3 text-sm font-semibold text-primary">A evidência aparecerá em tempo real</h2>
          <p className="mt-1 max-w-md text-sm leading-6 text-secondary">Inicie a execução para acompanhar recuperação, tokens, julgamento e persistência.</p>
        </div>
      </section>
    )
  }

  const latest = session.runs.at(-1)
  const output = streamedOutput || latest?.agent_output || ''
  const metrics = latest?.metrics
  const isActive = session.status === 'queued' || session.status === 'running'
  const totalExpectedRuns = session.request.case_ids.length * 3

  return (
    <section aria-labelledby="live-title" className="min-w-0 space-y-4">
      <div className="rounded-xl border border-border bg-panel">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-4">
          <div>
            <p className="font-mono text-xs text-muted">{session.session_id}</p>
            <h2 id="live-title" className="mt-1 text-lg font-semibold text-primary">Execução em tempo real</h2>
          </div>
          <span className="inline-flex items-center gap-2 rounded-full border border-border bg-canvas px-3 py-1 text-xs text-secondary" role="status" aria-live="polite">
            {isActive ? <Activity aria-hidden="true" className="size-3.5 animate-pulse text-accent" /> : <RotateCcw aria-hidden="true" className="size-3.5" />}
            {reconnecting ? 'Reconectando' : `${sessionLabels[session.status]} · ${session.runs.length}/${totalExpectedRuns} tentativas`}
          </span>
          {isActive ? <button type="button" disabled={cancelling} onClick={() => onCancel(session.session_id)} className="rounded-md border border-danger/40 px-3 py-1.5 text-xs text-danger disabled:opacity-50">Cancelar</button> : null}
        </header>

        <div className="grid gap-4 p-5 lg:grid-cols-[minmax(0,1fr)_13rem]">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-muted">Resposta do agente</p>
            <div className="mt-2 min-h-40 whitespace-pre-wrap rounded-lg border border-border bg-canvas p-4 text-sm leading-7 text-primary">
              {output || <span className="text-muted">Aguardando o primeiro token…</span>}
              {isActive && output ? <span aria-hidden="true" className="ml-1 inline-block h-4 w-1 animate-pulse bg-accent" /> : null}
            </div>
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-muted">Pipeline</p>
            <ol className="mt-3 space-y-2" aria-label="Eventos da sessão">
              {events.slice(-8).map((event, index) => (
                <li key={`${event}-${index}`} className="flex gap-2 text-xs leading-5 text-secondary">
                  <span aria-hidden="true" className="mt-1.5 size-1.5 shrink-0 rounded-full bg-accent" />
                  {eventLabels[event] ?? event}
                </li>
              ))}
            </ol>
          </div>
        </div>

        <div className="grid gap-2 border-t border-border p-4 sm:grid-cols-3">
          <LiveMetric label="TTFT" value={metrics?.time_to_first_token_ms ? `${metrics.time_to_first_token_ms} ms` : 'Aguardando'} icon={Clock3} />
          <LiveMetric label="Tokens" value={metrics?.total_tokens ? String(metrics.total_tokens) : 'Aguardando'} icon={Hash} />
          <LiveMetric label="Custo estimado" value={metrics?.cost_usd !== null && metrics?.cost_usd !== undefined ? `US$ ${metrics.cost_usd.toFixed(6)}` : 'Aguardando'} icon={Coins} />
        </div>
      </div>

      {Object.keys(session.case_statuses).length ? <section className="rounded-xl border border-border bg-panel p-5" aria-labelledby="case-results-title"><h2 id="case-results-title" className="text-sm font-semibold">Resultado agregado por caso</h2><p className="mt-1 text-xs leading-5 text-muted">Três resultados iguais indicam estabilidade; divergência ou tentativa ausente permanece visível.</p><ul className="mt-3 grid gap-2 sm:grid-cols-2">{Object.entries(session.case_statuses).map(([caseId, status]) => <li key={caseId} className="flex items-center justify-between gap-3 rounded-lg border border-border bg-canvas p-3"><span className="truncate font-mono text-xs text-secondary">{caseId}</span><span className={`flex shrink-0 items-center gap-1.5 text-xs font-medium ${status === 'stable_pass' ? 'text-success' : status === 'stable_fail' ? 'text-danger' : 'text-warning'}`}>{status === 'stable_pass' ? <CheckCircle2 aria-hidden="true" className="size-3.5" /> : status === 'stable_fail' ? <XCircle aria-hidden="true" className="size-3.5" /> : <AlertTriangle aria-hidden="true" className="size-3.5" />}{caseLabels[status] ?? status}</span></li>)}</ul></section> : null}

      {session.error ? <section className="rounded-xl border border-warning/30 bg-warning/8 p-4 text-sm text-warning" role="alert"><strong className="flex items-center gap-2"><AlertTriangle aria-hidden="true" className="size-4" />Execução inconclusiva por problema externo</strong><p className="mt-1 leading-6">{friendlySessionError(session.error)}</p><details className="mt-2"><summary className="cursor-pointer text-xs font-medium">Ver erro técnico</summary><pre className="mt-2 overflow-auto whitespace-pre-wrap rounded-md bg-canvas p-3 text-xs text-secondary">{session.error}</pre></details></section> : null}

      {session.runs.length ? (
        <div>
          <div className="mb-3 flex items-center gap-2">
            <h2 className="text-sm font-semibold text-primary">Tentativas e evidências</h2>
            <span className="rounded-full border border-border px-2 py-0.5 text-xs text-muted">{session.runs.length}/{totalExpectedRuns}</span>
          </div>
          <div className="space-y-3">
            {[...session.runs].reverse().map((run) => <RunDetail key={run.run_id} verdict={run} />)}
          </div>
        </div>
      ) : null}
      {summary ? <section className="rounded-xl border border-border bg-panel p-5" aria-labelledby="summary-title"><h2 id="summary-title" className="text-sm font-semibold">Resumo da sessão</h2><div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4"><LiveMetric label="Casos aprovados com estabilidade" value={`${summary.stable_passes}/${summary.total_cases}`} icon={Activity} /><LiveMetric label="Latência mediana / p95" value={`${summary.latency_p50_ms ?? '—'} / ${summary.latency_p95_ms ?? '—'} ms`} icon={Clock3} /><LiveMetric label="Tokens totais" value={String(summary.total_tokens)} icon={Hash} /><LiveMetric label="Custo conhecido" value={`US$ ${summary.known_cost_usd.toFixed(6)}`} icon={Coins} /></div>{summary.runs_without_cost ? <p className="mt-3 text-xs text-warning">{summary.runs_without_cost} tentativa(s) sem preço disponível; o total não é uma estimativa completa.</p> : null}</section> : null}
    </section>
  )
}
