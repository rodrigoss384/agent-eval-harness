import {
  evaluationSessionSchema,
  modelRoleListSchema,
  runListSchema,
  runVerdictSchema,
  sessionAcceptedSchema,
  sessionListSchema,
  datasetDocumentSchema,
  datasetMetadataListSchema,
  sessionSummarySchema,
  biasAcceptedSchema,
  biasAuditListSchema,
  biasAuditSchema,
  healthSchema,
} from './schemas'

async function readJson(response: Response): Promise<unknown> {
  if (!response.ok) {
    const problem = (await response.json().catch(() => null)) as { detail?: string } | null
    throw new Error(problem?.detail ?? 'Não foi possível concluir a solicitação.')
  }
  return response.json()
}

export async function listRuns() {
  return runListSchema.parse(await readJson(await fetch('/api/eval/runs')))
}

export async function listModels() {
  return modelRoleListSchema.parse(await readJson(await fetch('/api/models')))
}

export async function getHealth() {
  return healthSchema.parse(await readJson(await fetch('/api/health')))
}

export async function createOfflineRun(output: string) {
  const response = await fetch('/api/eval/run', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      case_id: 'case_001',
      methods: ['deterministic_match', 'programmatic_check'],
      candidate: { output, tool_calls: [] },
    }),
  })
  return runVerdictSchema.parse(await readJson(response))
}

export interface LiveSessionInput {
  datasetId: string
  caseIds: string[]
  mode: 'single' | 'suite'
  concurrency: number
  geminiPricingProfile: 'free' | 'paid_standard'
}

export async function createLiveSession(input: LiveSessionInput) {
  const response = await fetch('/api/eval/sessions', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      mode: input.mode,
      dataset_id: input.datasetId,
      case_ids: input.caseIds,
      methods: ['deterministic_match', 'llm_as_judge', 'programmatic_check'],
      judge_role: 'judge_alt',
      pricing_profiles: { agent: 'standard', judge: input.geminiPricingProfile },
      concurrency: input.concurrency,
      trials: 3,
    }),
  })
  return sessionAcceptedSchema.parse(await readJson(response))
}

export async function listSessions() {
  return sessionListSchema.parse(await readJson(await fetch('/api/eval/sessions')))
}

export async function getSession(sessionId: string) {
  return evaluationSessionSchema.parse(
    await readJson(await fetch(`/api/eval/sessions/${encodeURIComponent(sessionId)}`)),
  )
}

export async function listDatasets() {
  return datasetMetadataListSchema.parse(await readJson(await fetch('/api/eval/datasets')))
}

export async function getDataset(datasetId: string) {
  return datasetDocumentSchema.parse(await readJson(await fetch(`/api/eval/datasets/${encodeURIComponent(datasetId)}`)))
}

export async function importDataset(name: string, content: string) {
  const response = await fetch('/api/eval/datasets/import', {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ name, content, data_classification: 'synthetic' }),
  })
  return datasetDocumentSchema.parse(await readJson(response))
}

export async function getSessionSummary(sessionId: string) {
  return sessionSummarySchema.parse(await readJson(await fetch(`/api/eval/sessions/${encodeURIComponent(sessionId)}/summary`)))
}

export async function cancelSession(sessionId: string) {
  const response = await fetch(`/api/eval/sessions/${encodeURIComponent(sessionId)}/cancel`, { method: 'POST' })
  return evaluationSessionSchema.parse(await readJson(response))
}

export type BiasExperiment = 'position' | 'self-preference' | 'verbosity' | 'correctness-definition'
export async function createBiasAudit(experiment: BiasExperiment, datasetId: string, caseId: string) {
  const response = await fetch(`/api/eval/bias/${experiment}`, {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ dataset_id: datasetId, case_id: caseId }),
  })
  return biasAcceptedSchema.parse(await readJson(response))
}

export async function listBiasAudits() {
  return biasAuditListSchema.parse(await readJson(await fetch('/api/eval/bias')))
}

export async function getBiasAudit(auditId: string) {
  return biasAuditSchema.parse(await readJson(await fetch(`/api/eval/bias/${encodeURIComponent(auditId)}`)))
}

export function watchBiasAudit(auditId: string, onEvent: (event: LiveEvent) => void) {
  const source = new EventSource(`/api/eval/bias/${encodeURIComponent(auditId)}/events`)
  for (const name of ['snapshot', 'audit_started', 'measurement_completed', 'audit_completed', 'audit_failed']) {
    source.addEventListener(name, (event) => {
      const message = event as MessageEvent<string>
      onEvent({ type: name, payload: JSON.parse(message.data) as unknown })
      if (['audit_completed', 'audit_failed'].includes(name)) source.close()
    })
  }
  return () => source.close()
}

export interface LiveEvent {
  type: string
  payload: unknown
}

export function watchSession(
  sessionId: string,
  onEvent: (event: LiveEvent) => void,
  onConnectionError: () => void,
) {
  const source = new EventSource(`/api/eval/sessions/${encodeURIComponent(sessionId)}/events`)
  const eventNames = [
    'snapshot', 'session_started', 'case_started', 'retrieval_completed',
    'generation_started', 'generation_token', 'generation_completed',
    'evaluation_started', 'evaluation_completed', 'trial_completed',
    'trial_failed',
    'case_completed', 'session_completed', 'session_partial', 'session_failed',
    'session_cancelled',
    'session_interrupted',
  ]
  for (const name of eventNames) {
    source.addEventListener(name, (event) => {
      const message = event as MessageEvent<string>
      onEvent({ type: name, payload: JSON.parse(message.data) as unknown })
      if (['session_completed', 'session_partial', 'session_failed', 'session_cancelled', 'session_interrupted'].includes(name)) {
        source.close()
      }
    })
  }
  source.onerror = onConnectionError
  return () => source.close()
}
