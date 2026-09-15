import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { RunDetail } from './run-detail'
import type { RunVerdict } from './schemas'

const verdict: RunVerdict = {
  run_id: 'run_001',
  case_id: 'case_001',
  created_at: '2026-09-08T19:30:00Z',
  run_status: 'completed',
  final_verdict: 'pass',
  candidate_origin: 'supplied_trace',
  agent_input: 'Qual é a capital do Brasil?',
  agent_output: 'Brasília',
  tool_calls: [],
  evaluations: [
    {
      method: 'deterministic_match',
      status: 'passed',
      correctness_definition: 'A resposta deve ser exatamente “Brasília”.',
      passed: true,
      reason: 'O valor observado satisfaz a regra determinística declarada.',
      expected: 'Brasília',
      actual: 'Brasília',
      evidence: { rule_kind: 'exact' },
    },
  ],
  metrics: {
    latency_ms: 18,
    input_tokens: 5,
    output_tokens: 2,
    total_tokens: 7,
    cost_usd: null,
    cost_status: 'unavailable',
    cost_source: 'none',
  },
}

describe('RunDetail', () => {
  it('expõe definição de correto e racional ao expandir a avaliação', async () => {
    const user = userEvent.setup()
    render(<RunDetail verdict={verdict} />)

    expect(screen.getByRole('heading', { name: /case_001/ })).toBeInTheDocument()
    expect(screen.getAllByText('Brasília').length).toBeGreaterThan(0)
    expect(screen.getByText(/Trace fornecido.*não gerado por IA/i)).toBeInTheDocument()

    // Abrir o details
    const detailsSummary = screen.getByText(/Como cada método avaliou/i)
    await user.click(detailsSummary)

    const trigger = screen.getByRole('button', { name: /validação exata/i })
    expect(trigger).toHaveAttribute('aria-expanded', 'false')

    await user.click(trigger)

    expect(trigger).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getAllByText('A resposta deve ser exatamente “Brasília”.')[0]).toBeVisible()
    expect(screen.getAllByText(/satisfaz a regra determinística/)[0]).toBeVisible()
  })

  it('destaca a falha normativa quando o juiz e a regra determinística discordam', () => {
    render(<RunDetail verdict={{
      ...verdict,
      final_verdict: 'fail',
      evaluations: [
        { method: 'llm_as_judge', status: 'passed', correctness_definition: 'Avaliação semântica.', passed: true, reason: 'O juiz aceitou a resposta.', evidence: {}, score: 0.9, threshold: 0.8 },
        { method: 'deterministic_match', status: 'failed', correctness_definition: 'Correspondência exata.', passed: false, reason: 'A regra exata falhou.', evidence: {}, expected: 'Brasília', actual: 'Brasilia' },
      ],
    }} />)

    expect(screen.getByText('Os métodos discordaram.')).toBeInTheDocument()
    expect(screen.getByText('A regra exata falhou.')).toBeInTheDocument()
  })
})
