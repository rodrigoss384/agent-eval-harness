import { AlertTriangle, ArrowLeftRight, Braces, CheckCircle2, CircleMinus, Scale, TextQuote } from 'lucide-react'

import type { BiasAudit } from '../runs/schemas'

const titles: Record<BiasAudit['experiment'], string> = {
  position: 'A ordem mudou a avaliação?',
  self_preference: 'O modelo favoreceu sua própria família?',
  verbosity: 'O texto mais longo recebeu vantagem?',
  correctness_definition: 'A definição de correto mudou o resultado?',
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
}

function numbers(value: unknown): number[] {
  return Array.isArray(value) ? value.filter((item): item is number => typeof item === 'number') : []
}

function average(values: number[]) {
  return values.length ? values.reduce((total, value) => total + value, 0) / values.length : null
}

function formatScore(value: number | null) {
  return value === null ? '—' : value.toFixed(3)
}

function resultCopy(audit: BiasAudit) {
  if (audit.status === 'failed' || audit.result === 'inconclusive') return { icon: CircleMinus, label: 'Evidência insuficiente', className: 'border-warning/30 bg-warning/8 text-warning' }
  if (audit.experiment === 'correctness_definition') return audit.result === 'detected'
    ? { icon: ArrowLeftRight, label: 'O resultado mudou com a regra', className: 'border-accent/30 bg-accent/8 text-accent' }
    : { icon: CheckCircle2, label: 'O resultado permaneceu igual', className: 'border-success/30 bg-success/8 text-success' }
  return audit.result === 'detected'
    ? { icon: AlertTriangle, label: 'Sinal observado neste teste', className: 'border-warning/30 bg-warning/8 text-warning' }
    : { icon: CheckCircle2, label: 'Sinal não observado neste teste', className: 'border-success/30 bg-success/8 text-success' }
}

function friendlyError(error: string) {
  if (/timeout|timed out/i.test(error)) return 'O provider demorou além do limite. A auditoria foi preservada como inconclusiva.'
  if (/503|unavailable|high demand/i.test(error)) return 'O provider estava indisponível ou com alta demanda. A auditoria foi preservada como inconclusiva.'
  if (/configuration|api.key|não configurad/i.test(error)) return 'Falta configurar um provider necessário para este protocolo.'
  return 'A execução externa não terminou. O resultado foi preservado como inconclusivo.'
}

function PositionEvidence({ measurements }: { measurements: Record<string, unknown> }) {
  const first = numbers(measurements.good_score_position_1)
  const second = numbers(measurements.good_score_position_2)
  const inversions = typeof measurements.inversions === 'number' ? measurements.inversions : null
  return <div className="grid gap-3 sm:grid-cols-3"><EvidenceCard label="Resposta boa em 1º" value={formatScore(average(first))} detail={`${first.length} medições`} /><EvidenceCard label="Resposta boa em 2º" value={formatScore(average(second))} detail={`${second.length} medições`} /><EvidenceCard label="Inversões" value={inversions === null ? '—' : String(inversions)} detail="Mudanças de vencedor" /></div>
}

function VerbosityEvidence({ measurements }: { measurements: Record<string, unknown> }) {
  const concise = numbers(measurements.concise_scores)
  const inflated = numbers(measurements.inflated_scores)
  return <div className="grid gap-3 sm:grid-cols-2"><EvidenceCard label="Resposta concisa" value={formatScore(average(concise))} detail={`Média de ${concise.length} notas`} /><EvidenceCard label="Resposta expandida" value={formatScore(average(inflated))} detail={`Média de ${inflated.length} notas`} /></div>
}

function SelfPreferenceEvidence({ measurements }: { measurements: Record<string, unknown> }) {
  const pairs = Array.isArray(measurements.pairs) ? measurements.pairs : []
  const equivalent = typeof measurements.equivalent_pairs === 'number' ? measurements.equivalent_pairs : pairs.filter((item) => record(item).equivalent === true).length
  const advantages = pairs.map((item) => record(item).own_family_advantage).filter((item): item is number => typeof item === 'number')
  return <div className="grid gap-3 sm:grid-cols-3"><EvidenceCard label="Pares tentados" value={String(pairs.length)} detail="Até três repetições" /><EvidenceCard label="Pares equivalentes" value={String(equivalent)} detail="Passaram no controle factual" /><EvidenceCard label="Vantagem da própria família" value={formatScore(average(advantages))} detail="Média dos pares válidos" /></div>
}

function CorrectnessEvidence({ measurements }: { measurements: Record<string, unknown> }) {
  const exact = record(measurements.tool_exact)
  const canonical = record(measurements.tool_canonical)
  return <div className="grid gap-3 sm:grid-cols-2"><RuleCard title="Regra exata" status={String(exact.status ?? 'indisponível')} expected={String(exact.expected ?? '—')} actual={String(exact.actual ?? '—')} /><RuleCard title="Regra com aliases canônicos" status={String(canonical.status ?? 'indisponível')} expected={String(canonical.expected ?? '—')} actual={String(canonical.actual ?? '—')} /></div>
}

function EvidenceCard({ label, value, detail }: { label: string; value: string; detail: string }) {
  return <div className="rounded-lg border border-border bg-canvas p-4"><p className="text-xs text-muted">{label}</p><strong className="mt-1 block text-2xl text-primary">{value}</strong><p className="mt-1 text-xs text-secondary">{detail}</p></div>
}

function RuleCard({ title, status, expected, actual }: { title: string; status: string; expected: string; actual: string }) {
  const passed = status === 'passed'
  return <div className={`rounded-lg border p-4 ${passed ? 'border-success/30 bg-success/8' : 'border-danger/30 bg-danger/8'}`}><p className="text-xs font-semibold uppercase tracking-[0.1em] text-muted">{title}</p><strong className={`mt-2 flex items-center gap-2 text-sm ${passed ? 'text-success' : 'text-danger'}`}>{passed ? <CheckCircle2 aria-hidden="true" className="size-4" /> : <CircleMinus aria-hidden="true" className="size-4" />}{passed ? 'Aprovado' : 'Reprovado'}</strong><dl className="mt-3 space-y-2 text-xs text-secondary"><div><dt>Esperado</dt><dd className="mt-0.5 font-mono text-primary">{expected}</dd></div><div><dt>Observado</dt><dd className="mt-0.5 font-mono text-primary">{actual}</dd></div></dl></div>
}

export function BiasResult({ audit }: { audit: BiasAudit }) {
  const result = resultCopy(audit)
  const ResultIcon = result.icon
  const measurements = audit.measurements
  const evidenceIcon = audit.experiment === 'position' ? ArrowLeftRight : audit.experiment === 'verbosity' ? TextQuote : audit.experiment === 'self_preference' ? Scale : Braces
  const EvidenceIcon = evidenceIcon

  return (
    <article className="rounded-xl border border-border bg-panel p-5" aria-live="polite">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div><p className="font-mono text-xs text-muted">{audit.audit_id}</p><h2 className="mt-1 text-lg font-semibold">{titles[audit.experiment]}</h2></div>
        <span className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium ${result.className}`}><ResultIcon aria-hidden="true" className="size-3.5" />{audit.status === 'queued' || audit.status === 'running' ? 'Experimento em andamento' : result.label}</span>
      </header>

      {audit.error ? <div className="mt-4 rounded-lg border border-warning/30 bg-warning/8 p-4 text-sm text-warning"><strong className="flex items-center gap-2"><AlertTriangle aria-hidden="true" className="size-4" />A execução não terminou</strong><p className="mt-1 leading-6">{friendlyError(audit.error)}</p><details className="mt-2"><summary className="cursor-pointer text-xs font-medium">Ver erro técnico</summary><pre className="mt-2 overflow-auto whitespace-pre-wrap rounded-md bg-canvas p-3 text-xs text-secondary">{audit.error}</pre></details></div> : null}

      <div className="mt-5 grid gap-4 md:grid-cols-2">
        <div><p className="text-xs font-semibold uppercase tracking-[0.1em] text-muted">Pergunta investigada</p><p className="mt-1 text-sm leading-6 text-secondary">{audit.hypothesis}</p></div>
        <div><p className="text-xs font-semibold uppercase tracking-[0.1em] text-muted">Como foi testada</p><p className="mt-1 text-sm leading-6 text-secondary">{audit.protocol}</p></div>
      </div>

      <section aria-labelledby="evidence-title" className="mt-5"><h3 id="evidence-title" className="mb-3 flex items-center gap-2 text-sm font-semibold"><EvidenceIcon aria-hidden="true" className="size-4 text-accent" />Evidência observada</h3>{audit.experiment === 'position' ? <PositionEvidence measurements={measurements} /> : audit.experiment === 'verbosity' ? <VerbosityEvidence measurements={measurements} /> : audit.experiment === 'self_preference' ? <SelfPreferenceEvidence measurements={measurements} /> : <CorrectnessEvidence measurements={measurements} />}</section>

      <div className="mt-5 rounded-lg border border-border bg-canvas p-4"><p className="text-xs font-semibold uppercase tracking-[0.1em] text-muted">O que este resultado não prova</p><p className="mt-2 text-sm leading-6 text-secondary">{audit.limitations.join(' ') || 'A execução ainda não produziu limitações conclusivas. Um único experimento nunca prova comportamento geral do modelo.'}</p></div>

      <details className="group mt-4"><summary className="cursor-pointer text-sm font-medium text-accent">Ver medições completas em JSON</summary><pre className="mt-3 max-h-96 overflow-auto rounded-lg border border-border bg-canvas p-4 text-xs leading-5 text-secondary">{JSON.stringify(audit.measurements, null, 2)}</pre></details>
    </article>
  )
}
