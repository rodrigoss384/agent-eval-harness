import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { LivePreflight } from './live-preflight'

describe('LivePreflight', () => {
  it('expõe o custo operacional antes de iniciar seis chamadas reais', async () => {
    const user = userEvent.setup()
    const onStart = vi.fn()
    render(<LivePreflight
      pending={false}
      onStart={onStart}
      datasets={[{ dataset_id: 'builtin-v2', name: 'Suíte', source: 'builtin', data_classification: 'synthetic', case_count: 1, checksum: 'abc', created_at: '2026-09-09T00:00:00Z' }]}
      cases={[{ id: 'case_retrieval_advanced_001', category: 'retrieval', domain: 'finanças', difficulty: 'advanced', input: 'Pergunta', expected_output: 'Resposta', reference_context: [], correctness_definition: 'Regra', rubric: [], threshold: 0.8 }]}
      datasetId="builtin-v2"
      onDataset={vi.fn()}
      onImport={vi.fn()}
      importing={false}
    />)

    expect(screen.getByText('1 caso(s) × 3 tentativas')).toBeInTheDocument()
    expect(screen.getByText('6 chamadas reais')).toBeInTheDocument()
    expect(screen.getByText(/Agente.*Juiz LLM/i)).toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText('Juiz LLM'), 'judge_alt')
    await user.click(screen.getByText('Opções avançadas'))
    await user.selectOptions(screen.getByLabelText('Perfil de preço do juiz Gemini'), 'paid_standard')
    await user.click(screen.getByRole('button', { name: /revisar execução/i }))
    expect(onStart).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: /confirmar e iniciar 6 chamadas/i }))

    expect(onStart).toHaveBeenCalledWith(expect.objectContaining({ geminiPricingProfile: 'paid_standard', caseIds: ['case_retrieval_advanced_001'] }))
  })
})
