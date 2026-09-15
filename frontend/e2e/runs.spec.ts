import { expect, test } from '@playwright/test'

test('persiste e reabre um trace fornecido pelo histórico', async ({ page }) => {
  await page.goto('/runs?mode=demo')
  await page.getByRole('button', { name: /Executar exemplo aprovado/i }).click()
  const runId = (await page.getByText(/Run ID:/).first().textContent())?.replace('Run ID: ', '')
  expect(runId).toBeTruthy()
  await page.reload()
  await expect(page.getByText(runId!, { exact: true }).first()).toBeVisible()
  await expect(page.getByText(/Todos os critérios normativos disponíveis foram atendidos/i).first()).toBeVisible()
})

test('acompanha três tentativas reais pela interface', async ({ page }) => {
  test.skip(process.env.RUN_LIVE_UI !== '1', 'Defina RUN_LIVE_UI=1 para autorizar seis chamadas reais.')
  test.setTimeout(180_000)
  const existingSession = process.env.LIVE_SESSION_ID
  await page.goto(existingSession ? `/runs?mode=live&session=${existingSession}` : '/runs?mode=live')

  await expect(page.getByText('6 chamadas reais')).toBeVisible()
  if (!existingSession) {
    await page.getByRole('button', { name: /Revisar execução/ }).click()
    await page.getByRole('button', { name: /Confirmar e iniciar 6 chamadas/ }).click()
  }
  await expect(page.getByRole('heading', { name: 'Execução em tempo real' })).toBeVisible()
  await expect(page.getByRole('status')).toContainText(/Concluída · 3\/3 tentativas/i, { timeout: 150_000 })
  await expect(page.getByText(/Resultado agregado por caso/i)).toBeVisible()
})
