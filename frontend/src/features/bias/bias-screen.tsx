import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Activity, ArrowLeftRight, Braces, CheckCircle2, Coins, Scale, ShieldAlert, TextQuote } from 'lucide-react'
import { useEffect, useState } from 'react'

import { createBiasAudit, getBiasAudit, listBiasAudits, listModels, type BiasExperiment, watchBiasAudit } from '../runs/api'
import { biasAuditSchema, type BiasAudit } from '../runs/schemas'
import { BiasResult } from './bias-result'

const experiments: Array<{ id: BiasExperiment; key: BiasAudit['experiment']; title: string; technical: string; description: string; calls: number; icon: typeof Scale }> = [
  { id: 'correctness-definition', key: 'correctness_definition', title: 'A regra muda o resultado?', technical: 'Sensibilidade à definição de correto', description: 'Aplica uma regra exata e outra que aceita aliases ao mesmo trace.', calls: 0, icon: Braces },
  { id: 'position', key: 'position', title: 'A ordem muda a avaliação?', technical: 'Viés de posição', description: 'Compara as mesmas respostas em A/B e B/A por três repetições.', calls: 6, icon: ArrowLeftRight },
  { id: 'verbosity', key: 'verbosity', title: 'Texto longo recebe vantagem?', technical: 'Viés de verbosidade', description: 'Compara versões equivalentes, concisa e expandida, nas duas ordens.', calls: 6, icon: TextQuote },
  { id: 'self-preference', key: 'self_preference', title: 'O modelo prefere sua família?', technical: 'Preferência própria controlada', description: 'Duas famílias geram e julgam pares controlados e factualmente equivalentes.', calls: 18, icon: Scale },
]

function auditStatus(audit: BiasAudit) {
  if (audit.status === 'queued' || audit.status === 'running') return 'Em andamento'
  if (audit.status === 'failed' || audit.result === 'inconclusive') return 'Inconclusivo'
  if (audit.experiment === 'correctness_definition') return audit.result === 'detected' ? 'Mudou com a regra' : 'Não mudou'
  return audit.result === 'detected' ? 'Sinal observado' : 'Sinal não observado'
}

function roleLabel(role: string) {
  return role === 'agent' ? 'agente' : role === 'judge' ? 'juiz principal' : 'juiz alternativo'
}

export function BiasScreen({ selectedAuditId, onAudit }: { selectedAuditId: string | null; onAudit: (id: string) => void }) {
  const queryClient = useQueryClient()
  const [pendingExperiment, setPendingExperiment] = useState<BiasExperiment | null>(null)
  const audits = useQuery({ queryKey: ['bias-audits'], queryFn: listBiasAudits, refetchInterval: 10_000 })
  const models = useQuery({ queryKey: ['models'], queryFn: listModels, staleTime: 30_000 })
  const audit = useQuery({ queryKey: ['bias-audit', selectedAuditId], queryFn: () => getBiasAudit(selectedAuditId!), enabled: Boolean(selectedAuditId), refetchInterval: (query) => ['queued', 'running'].includes(query.state.data?.status ?? '') ? 2_000 : false })
  const create = useMutation({
    mutationFn: (experiment: BiasExperiment) => createBiasAudit(experiment, 'builtin-v2', experiment === 'correctness-definition' ? 'case_tool_001' : experiment === 'self-preference' ? 'case_factual_002' : 'case_retrieval_advanced_001'),
    onSuccess: (accepted) => { setPendingExperiment(null); onAudit(accepted.audit_id); void queryClient.invalidateQueries({ queryKey: ['bias-audits'] }) },
  })

  useEffect(() => {
    if (!selectedAuditId) return
    return watchBiasAudit(selectedAuditId, ({ type, payload }) => {
      if (type === 'snapshot' || type === 'audit_completed') {
        const parsed = biasAuditSchema.safeParse(payload)
        if (parsed.success) queryClient.setQueryData(['bias-audit', selectedAuditId], parsed.data)
      }
      if (type === 'measurement_completed' || type === 'audit_failed') void queryClient.invalidateQueries({ queryKey: ['bias-audit', selectedAuditId] })
    })
  }, [queryClient, selectedAuditId])

  const current = audit.data ?? audits.data?.find((item) => item.audit_id === selectedAuditId) ?? audits.data?.[0]
  const configured = new Set(models.data?.filter((model) => model.configured).map((model) => model.role) ?? [])

  function requirements(experiment: BiasExperiment) {
    if (experiment === 'correctness-definition') return []
    return experiment === 'self-preference' ? ['agent', 'judge', 'judge_alt'] : ['judge_alt']
  }

  function begin(experiment: BiasExperiment) {
    if (experiment === 'correctness-definition') create.mutate(experiment)
    else setPendingExperiment(experiment)
  }

  const pending = experiments.find((item) => item.id === pendingExperiment)
  const pendingMissing = pendingExperiment ? requirements(pendingExperiment).filter((role) => !configured.has(role as 'agent' | 'judge' | 'judge_alt')) : []

  return <div>
    <header className="mb-6 max-w-3xl"><p className="text-xs font-medium uppercase tracking-[0.14em] text-accent">Auditoria explicada</p><h1 className="mt-2 text-2xl font-semibold tracking-[-0.03em] sm:text-3xl">Descubra quando o avaliador pode ser influenciado</h1><p className="mt-2 text-sm leading-6 text-secondary">Cada protocolo responde uma pergunta limitada. O resultado vale para este caso, modelos e momento — não é uma conclusão geral sobre a IA.</p></header>

    <section className="mb-5 rounded-xl border border-accent/30 bg-accent/8 p-5" aria-labelledby="first-audit-title"><div className="flex flex-wrap items-start justify-between gap-4"><div className="max-w-2xl"><p className="text-xs font-semibold uppercase tracking-[0.12em] text-accent">Comece sem chaves e sem custo</p><h2 id="first-audit-title" className="mt-2 text-lg font-semibold">Veja como a definição de “correto” pode mudar um veredito</h2><p className="mt-2 text-sm leading-6 text-secondary">O mesmo nome de ferramenta falha numa regra exata e passa quando um alias autorizado é aceito. Isso demonstra sensibilidade à regra; não mede prevalência geral de viés.</p></div><button type="button" disabled={create.isPending} onClick={() => create.mutate('correctness-definition')} className="inline-flex shrink-0 items-center gap-2 rounded-md bg-accent px-4 py-2.5 text-sm font-semibold text-white hover:bg-accent-strong disabled:opacity-50"><Braces aria-hidden="true" className="size-4" />Executar experimento local</button></div></section>

    {create.isError ? <p role="alert" className="mb-4 rounded-lg border border-danger/30 bg-danger/8 p-3 text-sm text-danger">{create.error.message}</p> : null}

    <section aria-labelledby="protocols-title"><div className="mb-3"><h2 id="protocols-title" className="text-sm font-semibold">Todos os protocolos</h2><p className="mt-1 text-xs text-muted">Os protocolos com chamadas reais exigem confirmação.</p></div><div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">{experiments.map(({ id, title, technical, description, calls, icon: Icon }) => {
      const missing = requirements(id).filter((role) => !configured.has(role as 'agent' | 'judge' | 'judge_alt'))
      return <article key={id} className="flex flex-col rounded-xl border border-border bg-panel p-4"><Icon aria-hidden="true" className="size-4 text-accent" /><p className="mt-3 text-xs text-muted">{technical}</p><h3 className="mt-1 text-sm font-semibold">{title}</h3><p className="mt-2 min-h-12 text-xs leading-5 text-secondary">{description}</p><p className="mt-3 flex items-center gap-1.5 font-mono text-[11px] text-muted"><Coins aria-hidden="true" className="size-3" />{calls ? `${calls} chamadas externas` : '0 chamadas externas'}</p>{missing.length ? <p className="mt-2 text-xs leading-5 text-warning">Requer: {missing.map(roleLabel).join(', ')}</p> : null}<button type="button" disabled={create.isPending || models.isPending || missing.length > 0} onClick={() => begin(id)} className="mt-3 w-full rounded-md border border-border px-3 py-2 text-xs font-medium text-primary hover:border-accent disabled:cursor-not-allowed disabled:opacity-45">{calls ? 'Revisar protocolo' : 'Executar protocolo local'}</button></article>
    })}</div></section>

      {pending ? <section className="mt-4 rounded-xl border border-warning/30 bg-warning/8 p-4" aria-labelledby="confirm-audit-title"><div className="flex items-start gap-3"><ShieldAlert aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-warning" /><div><h2 id="confirm-audit-title" className="text-sm font-semibold text-primary">Confirmar {pending.calls} chamadas externas</h2><p className="mt-1 text-sm leading-6 text-secondary">O protocolo “{pending.title}” usa providers reais, pode gerar custo e não terá retry ou fallback automático.</p>{pendingMissing.length ? <p className="mt-2 text-sm text-warning">Configure antes: {pendingMissing.map(roleLabel).join(', ')}.</p> : null}<div className="mt-3 flex flex-wrap gap-2"><button type="button" onClick={() => setPendingExperiment(null)} className="rounded-md border border-border px-3 py-2 text-sm text-secondary">Cancelar</button><button type="button" disabled={create.isPending || pendingMissing.length > 0} onClick={() => create.mutate(pending.id)} className="rounded-md bg-accent px-3 py-2 text-sm font-semibold text-white disabled:opacity-50">Confirmar e executar</button></div></div></div></section> : null}

    <div className="mt-6 grid items-start gap-4 xl:grid-cols-[18rem_minmax(0,1fr)]">
      <section aria-labelledby="audit-history-title" className="overflow-hidden rounded-xl border border-border bg-panel"><div className="border-b border-border px-4 py-3"><h2 id="audit-history-title" className="text-xs font-semibold uppercase tracking-[0.12em] text-muted">Histórico de auditorias</h2></div>{audits.data?.length ? <ul className="max-h-[34rem] divide-y divide-border overflow-auto">{audits.data.map((item) => <li key={item.audit_id}><button type="button" aria-current={current?.audit_id === item.audit_id ? 'true' : undefined} onClick={() => onAudit(item.audit_id)} className="w-full px-4 py-3 text-left hover:bg-elevated aria-[current=true]:bg-elevated"><span className="block truncate text-sm font-medium text-primary">{experiments.find((experiment) => experiment.key === item.experiment)?.title}</span><span className="mt-1 flex items-center justify-between gap-2 text-xs"><span className="font-mono text-muted">{item.audit_id}</span><span className={item.status === 'failed' || item.result === 'inconclusive' ? 'text-warning' : 'text-secondary'}>{auditStatus(item)}</span></span></button></li>)}</ul> : <div className="p-6 text-center text-sm text-muted">Nenhuma auditoria executada.</div>}</section>
      {current ? <BiasResult audit={current} /> : <section className="grid min-h-64 place-items-center rounded-xl border border-dashed border-border bg-panel/50 p-8 text-center"><div><Activity aria-hidden="true" className="mx-auto size-5 text-muted" /><h2 className="mt-3 text-sm font-semibold">Execute o experimento local</h2><p className="mt-1 text-sm text-secondary">A hipótese, o protocolo, as medições e os limites aparecerão aqui.</p></div></section>}
    </div>
  </div>
}
