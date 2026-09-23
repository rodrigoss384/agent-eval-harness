import { expect, test } from '@playwright/test'
import { readFileSync } from 'node:fs'

const recorded = JSON.parse(readFileSync('../data/benchmark_example.json', 'utf8'))

test('explora a evidência real registrada sem iniciar chamadas e recalcula sensibilidade', async ({ page }) => {
  const paid: string[] = []
  page.on('request', request => { if (request.method() === 'POST') paid.push(request.url()) })
  await page.goto('/compare')
  await expect(page.getByRole('heading', { name: 'O que as medições mostram' })).toBeVisible()
  await expect(page.getByText('Evidência real registrada · não executada agora')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Sem racional textual', exact: true })).toBeVisible()
  await page.getByLabel(/Mostrar somente respostas com divergência/).check()
  await expect(page.getByLabel('Resposta avaliada')).toHaveValue('case_001-correct')
  await page.getByLabel('Ativar análise exploratória').check()
  await expect(page.getByLabel('Limiar exploratório:')).toBeVisible()
  await page.getByRole('slider').fill('0.5')
  await expect(page.getByText(/Limiar exploratório:/)).toContainText('0.50')
  await expect(page.getByText('Sem racional textual', { exact: true }).first()).toBeVisible()
  expect(paid).toEqual([])
})

test('mostra prontidão e contagem antes de qualquer cobrança', async ({ page }) => {
  await page.goto('/compare')
  await page.getByRole('button', { name: 'Nova comparação' }).click()
  await expect(page.getByRole('button', { name: 'Iniciar 288 chamadas pagas' })).toBeDisabled()
  await page.getByLabel('O que comparar').selectOption('case_001')
  await expect(page.getByRole('button', { name: 'Iniciar 12 chamadas pagas' })).toBeDisabled()
  await expect(page.getByText('Configuração necessária')).toBeVisible()
})

test('é responsivo, mantém foco e permite inspecionar fontes com teclado', async ({ page }) => {
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: 900 })
    await page.goto('/compare')
    await expect(page.getByRole('heading', { name: 'Inspecione os dois vereditos' })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.getByText('Ver ground truth, fontes e rubrica').focus()
    await page.keyboard.press('Enter')
    await expect(page.getByText('Ver ground truth, fontes e rubrica').locator('..')).toHaveAttribute('open', '')
  }
  await page.setViewportSize({ width: 1280, height: 900 })
  await page.evaluate(() => { document.documentElement.style.zoom = '2' })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

test('preserva os resultados parciais e cancela pela interface com API simulada', async ({ page }) => {
  let cancelled = false
  await page.route('**/api/eval/benchmarks/test-running', route => route.fulfill({ json: {
    ...recorded, benchmark_id: 'test-running', recorded: false,
    status: cancelled ? 'cancelled' : 'running', runs: recorded.runs.slice(0, 1), calls: recorded.calls.slice(0, 2),
  } }))
  await page.route('**/api/eval/benchmarks/test-running/summary', async route => {
    const response = await page.request.get('/api/eval/benchmarks/example/summary')
    await route.fulfill({ json: await response.json() })
  })
  await page.route('**/api/eval/benchmarks/test-running/cancel', route => {
    cancelled = true
    return route.fulfill({ json: { ...recorded, benchmark_id: 'test-running', recorded: false, status: 'cancelled', error: 'Reserva de chamada incerta preservada.' } })
  })
  await page.goto('/compare?benchmark=test-running')
  await expect(page.getByRole('progressbar')).toBeVisible()
  await page.getByRole('button', { name: 'Cancelar próximas chamadas' }).click()
  await expect(page.getByText('Cancelado', { exact: true })).toBeVisible()
  await expect(page.getByText('Reserva de chamada incerta preservada.')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'O que as medições mostram' })).toBeVisible()
})

test('mantém estados de erro e caminhos de histórico e datasets', async ({ page }) => {
  await page.goto('/compare?benchmark=ausente')
  await expect(page.getByRole('heading', { name: 'Nenhum resultado disponível' })).toBeVisible()
  await page.getByRole('link', { name: 'Histórico', exact: true }).click()
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  await page.getByRole('link', { name: 'Datasets', exact: true }).click()
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  await expect(page.getByRole('combobox').first()).toContainText('24 casos')
})
