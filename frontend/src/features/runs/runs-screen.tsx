import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, FlaskConical, LoaderCircle, Play, RefreshCw, XCircle } from 'lucide-react'
import { useEffect, useState } from 'react'

import { cancelSession, createLiveSession, createOfflineRun, getDataset, getSession, getSessionSummary, importDataset, listDatasets, listModels, listRuns, listSessions, watchSession } from './api'
import { LivePreflight } from './live-preflight'
import { LiveSessionPanel } from './live-session-panel'
import { RunDetail } from './run-detail'
import { RunList } from './run-list'
import { SessionList } from './session-list'
import { evaluationSessionSchema } from './schemas'

interface RunsScreenProps {
  selectedRunId: string | null
  selectedSessionId: string | null
  selectedDatasetId: string | null
  mode: 'demo' | 'live'
  onSelect: (runId: string) => void
  onSession: (sessionId: string) => void
  onDataset: (datasetId: string) => void
  onMode: (mode: 'demo' | 'live') => void
}

export function RunsScreen({ selectedRunId, selectedSessionId, selectedDatasetId, mode, onSelect, onSession, onDataset, onMode }: RunsScreenProps) {
  const queryClient = useQueryClient()
  const [streamedOutput, setStreamedOutput] = useState('')
  const [events, setEvents] = useState<string[]>([])
  const [reconnecting, setReconnecting] = useState(false)
  const runsQuery = useQuery({ queryKey: ['runs'], queryFn: listRuns, refetchInterval: 30_000 })
  const sessionsQuery = useQuery({ queryKey: ['sessions'], queryFn: listSessions, refetchInterval: 15_000 })
  const datasetsQuery = useQuery({ queryKey: ['datasets'], queryFn: listDatasets })
  const modelsQuery = useQuery({ queryKey: ['models'], queryFn: listModels, staleTime: 30_000 })
  const datasetId = selectedDatasetId ?? datasetsQuery.data?.[0]?.dataset_id ?? 'builtin-v2'
  const datasetQuery = useQuery({ queryKey: ['dataset', datasetId], queryFn: () => getDataset(datasetId) })
  const effectiveSessionId = selectedSessionId ?? sessionsQuery.data?.[0]?.session_id ?? null
  const sessionQuery = useQuery({
    queryKey: ['session', effectiveSessionId],
    queryFn: () => getSession(effectiveSessionId!),
    enabled: Boolean(effectiveSessionId && mode === 'live'),
    refetchInterval: (query) => ['queued', 'running'].includes(query.state.data?.status ?? '') ? 5_000 : false,
  })
  const liveSession = sessionQuery.data ?? sessionsQuery.data?.find((item) => item.session_id === effectiveSessionId) ?? null
  const summaryQuery = useQuery({ queryKey: ['session-summary', effectiveSessionId], queryFn: () => getSessionSummary(effectiveSessionId!), enabled: Boolean(effectiveSessionId && liveSession && !['queued', 'running'].includes(liveSession.status)) })

  const createRun = useMutation({
    mutationFn: createOfflineRun,
    onSuccess: async (run) => {
      await queryClient.invalidateQueries({ queryKey: ['runs'] })
      onSelect(run.run_id)
    },
  })
  const createLive = useMutation({
    mutationFn: createLiveSession,
    onSuccess: async (accepted) => {
      setEvents([])
      setStreamedOutput('')
      await queryClient.invalidateQueries({ queryKey: ['sessions'] })
      onSession(accepted.session_id)
    },
  })
  const importMutation = useMutation({
    mutationFn: async (file: File) => importDataset(file.name.replace(/\.jsonl$/i, ''), await file.text()),
    onSuccess: async (document) => {
      await queryClient.invalidateQueries({ queryKey: ['datasets'] })
      queryClient.setQueryData(['dataset', document.metadata.dataset_id], document)
      onDataset(document.metadata.dataset_id)
    },
  })
  const cancelMutation = useMutation({ mutationFn: cancelSession, onSuccess: (session) => queryClient.setQueryData(['session', session.session_id], session) })

  useEffect(() => {
    if (!effectiveSessionId || !liveSession || mode !== 'live') return
    setReconnecting(false)
    return watchSession(effectiveSessionId, ({ type, payload }) => {
      setReconnecting(false)
      if (type !== 'generation_token' && type !== 'snapshot') setEvents((current) => [...current, type])
      if (type === 'generation_started') setStreamedOutput('')
      if (type === 'generation_token') {
        const token = (payload as { token?: unknown }).token
        if (typeof token === 'string') setStreamedOutput((current) => current + token)
      }
      if (type === 'snapshot') {
        const parsed = evaluationSessionSchema.safeParse(payload)
        if (parsed.success) queryClient.setQueryData(['session', effectiveSessionId], parsed.data)
      }
      if (['trial_completed', 'session_completed', 'session_partial', 'session_failed'].includes(type)) {
        void Promise.all([
          queryClient.invalidateQueries({ queryKey: ['session', effectiveSessionId] }),
          queryClient.invalidateQueries({ queryKey: ['sessions'] }),
          queryClient.invalidateQueries({ queryKey: ['runs'] }),
        ])
      }
    }, () => setReconnecting(true))
  }, [effectiveSessionId, liveSession?.status, mode, queryClient])

  if (runsQuery.isPending || sessionsQuery.isPending || datasetsQuery.isPending || datasetQuery.isPending || modelsQuery.isPending) {
    return <div className="flex min-h-72 items-center justify-center text-sm text-secondary" role="status"><LoaderCircle aria-hidden="true" className="mr-2 size-4 animate-spin" />Carregando ambiente de avaliação…</div>
  }
  if (runsQuery.isError || sessionsQuery.isError || datasetsQuery.isError || datasetQuery.isError || modelsQuery.isError) {
    const error = runsQuery.error ?? sessionsQuery.error ?? datasetsQuery.error ?? datasetQuery.error ?? modelsQuery.error
    return <div className="rounded-xl border border-danger/30 bg-danger/8 p-5" role="alert"><AlertTriangle aria-hidden="true" className="size-5 text-danger" /><h2 className="mt-3 font-semibold text-primary">Não foi possível carregar o laboratório</h2><p className="mt-1 text-sm text-secondary">{error?.message}</p><button className="mt-4 inline-flex items-center gap-2 rounded-md border border-border px-3 py-2 text-sm text-primary" onClick={() => { void runsQuery.refetch(); void sessionsQuery.refetch(); void datasetsQuery.refetch() }} type="button"><RefreshCw aria-hidden="true" className="size-4" />Tentar novamente</button></div>
  }

  const allRuns = runsQuery.data ?? []
  const manualRuns = allRuns.filter((run) => run.candidate_origin === 'supplied_trace')
  const selectedManual = manualRuns.find((run) => run.run_id === selectedRunId) ?? manualRuns[0] ?? null
  const requiredRoles = ['agent', 'judge_alt']
  const missingProviders = requiredRoles.filter((role) => !modelsQuery.data?.some((model) => model.role === role && model.configured)).map((role) => {
    const model = modelsQuery.data?.find((item) => item.role === role)
    const key = model?.provider ? `${model.provider.toUpperCase()}_API_KEY` : 'a chave do provider'
    const label = role === 'agent' ? 'agente' : 'juiz alternativo'
    return `${label} (${key})`
  })

  return (
    <div>
      <header className="mb-6 max-w-3xl"><p className="text-xs font-medium uppercase tracking-[0.14em] text-accent">Laboratório de avaliações</p><h1 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-primary sm:text-3xl">Veja o avaliador trabalhando</h1><p className="mt-2 text-sm leading-6 text-secondary">Comece sem chaves para aprender o fluxo ou use providers reais para avaliar três tentativas do mesmo caso.</p></header>

      <div className="mb-6 inline-flex rounded-lg border border-border bg-panel p-1" role="group" aria-label="Modo de avaliação">
        <button type="button" aria-pressed={mode === 'demo'} onClick={() => onMode('demo')} className="rounded-md px-4 py-2 text-sm font-medium text-secondary aria-pressed:bg-elevated aria-pressed:text-primary">Demonstração local</button>
        <button type="button" aria-pressed={mode === 'live'} onClick={() => onMode('live')} className="rounded-md px-4 py-2 text-sm font-medium text-secondary aria-pressed:bg-elevated aria-pressed:text-primary">Execução com IA real</button>
      </div>

      {createRun.isError || createLive.isError || importMutation.isError ? <p className="mb-4 rounded-lg border border-danger/30 bg-danger/8 p-3 text-sm text-danger" role="alert">{(createRun.error ?? createLive.error ?? importMutation.error)?.message}</p> : null}

      {mode === 'demo' ? (
        <>
          <section className="grid gap-4 xl:grid-cols-[22rem_minmax(0,1fr)]" aria-labelledby="demo-title">
            <div className="rounded-xl border border-accent/35 bg-panel p-5">
              <div className="flex items-center gap-2 text-accent"><FlaskConical aria-hidden="true" className="size-4" /><p className="text-xs font-semibold uppercase tracking-[0.14em]">Sem chave · sem custo</p></div>
              <h2 id="demo-title" className="mt-3 text-lg font-semibold">Compare um sucesso e uma falha</h2>
              <p className="mt-2 text-sm leading-6 text-secondary">O desafio é “Qual é a capital do Brasil?”. A regra exige exatamente “Brasília”. Escolha uma resposta e o backend real calculará o veredito.</p>
              <div className="mt-5 space-y-3">
                <button type="button" disabled={createRun.isPending} onClick={() => createRun.mutate('Brasília')} className="w-full rounded-lg border border-success/35 bg-success/8 p-4 text-left hover:border-success disabled:opacity-50"><span className="flex items-center gap-2 text-sm font-semibold text-success"><CheckCircle2 aria-hidden="true" className="size-4" />Executar exemplo aprovado</span><span className="mt-1 block text-xs text-secondary">Resposta enviada: “Brasília”</span></button>
                <button type="button" disabled={createRun.isPending} onClick={() => createRun.mutate('São Paulo')} className="w-full rounded-lg border border-danger/35 bg-danger/8 p-4 text-left hover:border-danger disabled:opacity-50"><span className="flex items-center gap-2 text-sm font-semibold text-danger"><XCircle aria-hidden="true" className="size-4" />Executar exemplo reprovado</span><span className="mt-1 block text-xs text-secondary">Resposta enviada: “São Paulo”</span></button>
              </div>
              <p className="mt-4 text-xs leading-5 text-muted">Esses traces são fornecidos pelo projeto, passam pelo avaliador real e entram no histórico local. Eles não são apresentados como geração de uma IA.</p>
            </div>
            {selectedManual ? <RunDetail verdict={selectedManual} /> : <div className="grid min-h-72 place-items-center rounded-xl border border-dashed border-border bg-panel/50 p-8 text-center"><div><Play aria-hidden="true" className="mx-auto size-5 text-muted" /><h2 className="mt-3 text-sm font-semibold">Escolha um dos exemplos</h2><p className="mt-1 max-w-md text-sm leading-6 text-secondary">O resultado aparecerá aqui com a regra, o observado e a justificativa.</p></div></div>}
          </section>
          <section className="mt-8" aria-labelledby="manual-history-title"><h2 id="manual-history-title" className="mb-3 text-sm font-semibold">Histórico de demonstrações e traces fornecidos</h2><div className="max-w-xl"><RunList runs={manualRuns} selectedRunId={selectedManual?.run_id ?? null} onSelect={onSelect} /></div></section>
        </>
      ) : (
        <>
          <div className="grid items-start gap-4 xl:grid-cols-[22rem_minmax(0,1fr)]">
            <LivePreflight pending={createLive.isPending} datasets={datasetsQuery.data ?? []} cases={datasetQuery.data?.cases ?? []} datasetId={datasetId} onDataset={onDataset} onStart={(input) => createLive.mutate(input)} onImport={(file) => importMutation.mutate(file)} importing={importMutation.isPending} providerReady={missingProviders.length === 0} missingProviders={missingProviders} />
            <LiveSessionPanel session={liveSession} summary={summaryQuery.data ?? null} streamedOutput={streamedOutput} events={events} reconnecting={reconnecting} onCancel={(id) => cancelMutation.mutate(id)} cancelling={cancelMutation.isPending} />
          </div>
          <section className="mt-8" aria-labelledby="session-history-title"><h2 id="session-history-title" className="mb-3 text-sm font-semibold">Histórico de execuções com IA</h2><div className="max-w-2xl"><SessionList sessions={sessionsQuery.data ?? []} selectedSessionId={effectiveSessionId} onSelect={onSession} /></div></section>
        </>
      )}
    </div>
  )
}
