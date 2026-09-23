import { z } from 'zod'

export const evaluationMetricsSchema = z.object({
  latency_ms: z.number().nullable(), queue_ms: z.number().nullable(),
  input_tokens: z.number().nullable(), output_tokens: z.number().nullable(), total_tokens: z.number().nullable(),
  cached_input_tokens: z.number().nullable().optional(), cost_usd: z.number().nullable(),
  cost_status: z.enum(['reported', 'estimated', 'unavailable']),
  cost_source: z.enum(['provider_response', 'pricing_catalog', 'mixed', 'none']),
  cost_formula: z.string().nullable().optional(), pricing_version: z.string().nullable().optional(),
})


export const evaluationSchema = z.object({
  method: z.enum(['deterministic_match', 'programmatic_check', 'llm_as_judge', 'decision_model']),
  status: z.enum(['passed', 'failed', 'observed', 'unavailable', 'error']),
  correctness_definition: z.string(),
  passed: z.boolean().nullable().optional(),
  reason: z.string(),
  expected: z.string().nullable().optional(),
  actual: z.string().nullable().optional(),
  evidence: z.record(z.string(), z.unknown()),
  judge_model: z.string().nullable().optional(),
  rubric: z.array(z.string()).optional(),
  score: z.number().nullable().optional(),
  threshold: z.number().nullable().optional(),
  metrics: evaluationMetricsSchema.nullable().optional(),
  judge_provider: z.string().nullable().optional(), upstream_provider: z.string().nullable().optional(),
  request_id: z.string().nullable().optional(), score_type: z.enum(['probability', 'rating']).nullable().optional(),
  rationale_available: z.boolean().nullable().optional(), protocol_version: z.string().nullable().optional(),
  evaluated_state: z.string().nullable().optional(),
})

export const runVerdictSchema = z.object({
  run_id: z.string(),
  case_id: z.string(),
  created_at: z.string(),
  run_status: z.enum(['completed', 'partial', 'failed']),
  final_verdict: z.enum(['pass', 'fail', 'inconclusive']),
  candidate_origin: z.enum(['supplied_trace', 'live_model']),
  agent_input: z.string(),
  agent_output: z.string(),
  tool_calls: z.array(
    z.object({ name: z.string(), arguments: z.record(z.string(), z.unknown()) }),
  ),
  evaluations: z.array(evaluationSchema),
  metrics: z.object({
    latency_ms: z.number().nullable(),
    input_tokens: z.number().nullable(),
    output_tokens: z.number().nullable(),
    total_tokens: z.number().nullable(),
    cost_usd: z.number().nullable(),
    cost_status: z.enum(['reported', 'estimated', 'unavailable']),
    cost_source: z.enum(['provider_response', 'pricing_catalog', 'mixed', 'none']),
    time_to_first_token_ms: z.number().nullable().optional(),
    generation_ms: z.number().nullable().optional(),
    judge_ms: z.number().nullable().optional(),
    total_latency_ms: z.number().nullable().optional(),
    cost_formula: z.string().nullable().optional(),
    pricing_version: z.string().nullable().optional(),
    agent_metrics: evaluationMetricsSchema.nullable().optional(),
  }),
  session_id: z.string().nullable().optional(),
  trial_index: z.number().nullable().optional(),
  agent_provider: z.string().nullable().optional(),
  agent_model: z.string().nullable().optional(),
  judge_provider: z.string().nullable().optional(),
  judge_model: z.string().nullable().optional(),
  retrieved_context: z.array(z.record(z.string(), z.unknown())).optional(),
})

export const runListSchema = z.array(runVerdictSchema)

export const modelRoleListSchema = z.array(
  z.object({
    role: z.enum(['agent', 'judge', 'judge_alt']),
    provider: z.string().nullable(),
    model: z.string().nullable(),
    configured: z.boolean(),
    base_url: z.string().nullable(),
  }),
)

export const healthSchema = z.object({
  status: z.string(),
  database: z.string(),
  version: z.string(),
})

export type RunVerdict = z.infer<typeof runVerdictSchema>
export type ModelRole = z.infer<typeof modelRoleListSchema>[number]
export type HealthStatus = z.infer<typeof healthSchema>

export const sessionAcceptedSchema = z.object({
  session_id: z.string(),
  status: z.literal('queued'),
  events_url: z.string(),
  calls_planned: z.number(),
})

export const evaluationSessionSchema = z.object({
  session_id: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
  status: z.enum(['queued', 'running', 'completed', 'partial', 'failed', 'cancelled', 'interrupted']),
  request: z.object({
    mode: z.enum(['single', 'suite']),
    dataset_id: z.string(),
    case_ids: z.array(z.string()),
    methods: z.array(z.enum(['deterministic_match', 'programmatic_check', 'llm_as_judge', 'decision_model'])),
    judge_role: z.enum(['judge', 'judge_alt']),
    pricing_profiles: z.record(z.string(), z.string()),
    concurrency: z.number(),
    trials: z.literal(3),
  }),
  runs: z.array(runVerdictSchema),
  case_statuses: z.record(z.string(), z.enum(['stable_pass', 'stable_fail', 'unstable', 'inconclusive'])),
  final_verdict: z.enum(['pass', 'fail', 'inconclusive']),
  current_case_id: z.string().nullable(),
  current_trial: z.number().nullable(),
  error: z.string().nullable(),
  event_cursor: z.number(),
})

export const sessionListSchema = z.array(evaluationSessionSchema)
export type EvaluationSession = z.infer<typeof evaluationSessionSchema>

const contextChunkSchema = z.object({ id: z.string(), text: z.string() })
export const datasetCaseSchema = z.object({
  id: z.string(),
  category: z.enum(['factual', 'retrieval', 'tool_use']),
  domain: z.string(),
  difficulty: z.enum(['basic', 'intermediate', 'advanced']),
  input: z.string(),
  expected_output: z.string(),
  reference_context: z.array(contextChunkSchema),
  correctness_definition: z.string(),
  rubric: z.array(z.string()),
  threshold: z.number(),
  expected_tool: z.string().nullable().optional(),
})

export const datasetMetadataSchema = z.object({
  dataset_id: z.string(),
  name: z.string(),
  source: z.enum(['builtin', 'imported']),
  data_classification: z.literal('synthetic'),
  case_count: z.number(),
  checksum: z.string(),
  created_at: z.string(),
})
export const datasetMetadataListSchema = z.array(datasetMetadataSchema)
export const datasetDocumentSchema = z.object({
  metadata: datasetMetadataSchema,
  cases: z.array(datasetCaseSchema),
})
export type DatasetCase = z.infer<typeof datasetCaseSchema>
export type DatasetMetadata = z.infer<typeof datasetMetadataSchema>

export const sessionSummarySchema = z.object({
  session_id: z.string(), total_cases: z.number(), total_runs: z.number(),
  stable_passes: z.number(), stable_fails: z.number(), unstable: z.number(),
  inconclusive: z.number(), stable_pass_rate: z.number(),
  latency_p50_ms: z.number().nullable(), latency_p95_ms: z.number().nullable(),
  total_tokens: z.number(), known_cost_usd: z.number(), runs_without_cost: z.number(),
  judge_scores: z.array(z.number()),
  methods: z.record(z.string(), z.object({ calls: z.number(), valid: z.number(), errors: z.number(),
    latency_p50_ms: z.number().nullable(), latency_p95_ms: z.number().nullable(),
    known_cost_usd: z.number(), calls_without_cost: z.number(),
    reported_cost_usd: z.number(), estimated_cost_usd: z.number() })).optional(),
  comparison: z.object({ paired_trials: z.number(), agreements: z.number(), disagreements: z.number(),
    agreement_rate: z.number().nullable(), unpaired_trials: z.number() }).optional(),
})
export type SessionSummary = z.infer<typeof sessionSummarySchema>

export const biasAuditSchema = z.object({
  audit_id: z.string(),
  experiment: z.enum(['position', 'self_preference', 'verbosity', 'correctness_definition']),
  created_at: z.string(), updated_at: z.string(),
  status: z.enum(['queued', 'running', 'completed', 'failed', 'cancelled', 'interrupted']),
  result: z.enum(['detected', 'not_detected', 'inconclusive']),
  hypothesis: z.string(), protocol: z.string(), calls_planned: z.number(),
  measurements: z.record(z.string(), z.unknown()), delta: z.number().nullable(),
  limitations: z.array(z.string()), error: z.string().nullable(), event_cursor: z.number(),
})
export const biasAuditListSchema = z.array(biasAuditSchema)
export const biasAcceptedSchema = z.object({
  audit_id: z.string(), status: z.literal('queued'), events_url: z.string(), calls_planned: z.number(),
})
export type BiasAudit = z.infer<typeof biasAuditSchema>
