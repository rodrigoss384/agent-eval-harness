import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { BiasAudit } from '../runs/schemas'
import { BiasResult } from './bias-result'

const base: BiasAudit = {
  audit_id: 'audit_001', experiment: 'correctness_definition', created_at: '2026-09-14T00:00:00Z', updated_at: '2026-09-14T00:00:01Z', status: 'completed', result: 'detected', hypothesis: 'A regra pode mudar o resultado.', protocol: 'Compara duas regras.', calls_planned: 0, delta: 1, limitations: ['Não mede prevalência geral.'], error: null, event_cursor: 1,
  measurements: {
    tool_exact: { status: 'failed', expected: 'get_customer', actual: 'buscar_cliente' },
    tool_canonical: { status: 'passed', expected: 'get_customer', actual: 'buscar_cliente' },
  },
}

describe('BiasResult', () => {
  it('explica sensibilidade à regra sem afirmar viés geral', () => {
    render(<BiasResult audit={base} />)
    expect(screen.getByText('O resultado mudou com a regra')).toBeInTheDocument()
    expect(screen.getByText('Regra exata')).toBeInTheDocument()
    expect(screen.getByText('Regra com aliases canônicos')).toBeInTheDocument()
    expect(screen.getByText('Não mede prevalência geral.')).toBeInTheDocument()
  })

  it('traduz indisponibilidade externa como evidência insuficiente', () => {
    render(<BiasResult audit={{ ...base, experiment: 'position', status: 'failed', result: 'inconclusive', measurements: {}, error: 'OpenAIAPIError: 503 UNAVAILABLE high demand' }} />)
    expect(screen.getByText('Evidência insuficiente')).toBeInTheDocument()
    expect(screen.getByText(/provider estava indisponível/i)).toBeInTheDocument()
  })
})
