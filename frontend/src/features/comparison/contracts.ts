import { z } from 'zod'
import { datasetCaseSchema, evaluationSchema } from '../runs/schemas'

export const benchmarkSampleSchema = z.object({
  id: z.string(), case: datasetCaseSchema, output: z.string(),
  expected_passed: z.boolean(), label_reason: z.string(),
  tool_calls: z.array(z.object({ name: z.string(), arguments: z.record(z.string(), z.unknown()) })),
})
export const benchmarkSchema = z.object({
  benchmark_id: z.string(), status: z.string(), created_at: z.string(), updated_at: z.string(),
  recorded: z.boolean(), error: z.string().nullable(), calls_planned: z.number(),
  protocol_version: z.string(), dataset_version: z.string(), dataset_checksum: z.string(),
  samples: z.array(benchmarkSampleSchema),
  request: z.object({ max_calls: z.number(), max_cost_usd: z.number() }),
  runs: z.array(z.object({ sample_id: z.string(), trial_index: z.number(), evaluations: z.array(evaluationSchema) })),
  calls: z.array(z.object({ sample_id: z.string(), trial_index: z.number(), method: z.string(),
    status: z.string(), reserved_usd: z.number(), accounted_usd: z.number(), accounting: z.string(),
    started_at: z.string(), completed_at: z.string().nullable() })),
  accounted_usd: z.number(), configuration: z.record(z.string(), z.unknown()),
})
const reliability = z.object({ lower: z.number(), upper: z.number(), count: z.number(),
  mean_probability: z.number().nullable(), observed_frequency: z.number().nullable() })
export const methodStatsSchema = z.object({
  calls: z.number().optional(), valid: z.number().optional(), errors: z.number().optional(), timeouts: z.number().optional(),
  latency_p50_ms: z.number().nullable().optional(), latency_p95_ms: z.number().nullable().optional(),
  known_cost_usd: z.number().optional(), reported_cost_usd: z.number().optional(), estimated_cost_usd: z.number().optional(),
  calls_without_cost: z.number().optional(), input_tokens: z.number().optional(), output_tokens: z.number().optional(),
  calls_without_tokens: z.number().optional(), distinct_candidates: z.number(), expected_candidates: z.number(),
  complete_candidates: z.number(), accuracy: z.number().nullable(), precision: z.number().nullable(),
  recall: z.number().nullable(), f1: z.number().nullable(), confusion: z.object({ tp: z.number(), tn: z.number(), fp: z.number(), fn: z.number() }),
  unstable_candidates: z.number(), mean_score_stddev: z.number().nullable(), brier_score: z.number().nullable(),
  reliability: z.array(reliability), models: z.array(z.string()).optional(), providers: z.array(z.string()).optional(),
})
export const benchmarkSummarySchema = z.object({
  benchmark_id: z.string(), status: z.string(), distinct_cases: z.number(), distinct_candidates: z.number(), trials: z.number(),
  methods: z.record(z.string(), methodStatsSchema),
  comparison: z.object({ paired_trials: z.number(), agreements: z.number(), disagreements: z.number(), agreement_rate: z.number().nullable(), unpaired_trials: z.number() }),
  exploratory_threshold: z.number().nullable(), accounted_usd: z.number(), calls_attempted: z.number(), uncertain_calls: z.number(),
  weighting: z.string(), limitations: z.array(z.string()),
})
export const benchmarkListSchema = z.array(z.object({ benchmark_id: z.string(), created_at: z.string(), status: z.string(), calls_planned: z.number(), calls_attempted: z.number(), accounted_usd: z.number(), distinct_cases: z.number() }))
export const preflightSchema = z.object({ ready: z.boolean(), jev_ready: z.boolean(), issues: z.array(z.string()), max_calls: z.number(), max_cost_usd: z.number(), calls_planned: z.number() })
export type Benchmark = z.infer<typeof benchmarkSchema>
export type BenchmarkSummary = z.infer<typeof benchmarkSummarySchema>
export type MethodStats = z.infer<typeof methodStatsSchema>
export type Evaluation = z.infer<typeof evaluationSchema>

async function json(path: string, init?: RequestInit): Promise<unknown> {
  const response = await fetch(`/api/eval/benchmarks${path}`, init)
  const data: unknown = await response.json()
  if (!response.ok) {
    const error = data as { detail?: unknown }
    throw new Error(typeof error.detail === 'string' ? error.detail : 'Não foi possível carregar a comparação.')
  }
  return data
}
export const getPreflight = async () => preflightSchema.parse(await json('/preflight'))
export const getSamples = async () => z.array(benchmarkSampleSchema).parse(await json('/samples'))
export const getBenchmarks = async () => benchmarkListSchema.parse(await json(''))
export const getBenchmark = async (id: string) => benchmarkSchema.parse(await json(`/${encodeURIComponent(id)}`))
export const getBenchmarkSummary = async (id: string, threshold?: number) => benchmarkSummarySchema.parse(await json(`/${encodeURIComponent(id)}/summary${threshold == null ? '' : `?threshold=${threshold}`}`))
export const cancelBenchmark = async (id: string) => benchmarkSchema.parse(await json(`/${encodeURIComponent(id)}/cancel`, { method: 'POST' }))
export const createBenchmark = async (caseId: string) => z.object({ benchmark_id: z.string() }).parse(await json('', {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ confirm_paid: true, case_ids: caseId === 'all' ? null : [caseId], max_calls: 300, max_cost_usd: 2 }),
}))
