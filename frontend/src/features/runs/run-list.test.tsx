import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { RunList } from './run-list'

describe('RunList', () => {
  it('explica o estado vazio e orienta a primeira execução', () => {
    render(<RunList runs={[]} selectedRunId={null} onSelect={() => undefined} />)

    expect(screen.getByText('Nenhum teste registrado')).toBeInTheDocument()
    expect(screen.getByText(/execute um caso de teste/i)).toBeInTheDocument()
  })
})
