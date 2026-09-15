import { expect, test } from '@playwright/test'

test('orienta o primeiro acesso e mantém a execução live opcional', async ({ page }) => {
  await page.goto('/')
  await expect(page).toHaveTitle('Agent Eval Harness')
  await expect(page.locator('link[rel="icon"][href^="/agent-eval-mark.svg"]')).toHaveCount(1)
  await expect(page.locator('img[src^="/agent-eval-mark.svg"]')).toBeVisible()
  await expect(page.getByRole('heading', { name: /Entenda por que uma avaliação passou ou falhou/i })).toBeVisible()
  await expect(page.getByRole('link', { name: /Abrir demonstração/i })).toBeVisible()
  await expect(page.getByText('Configuração opcional pendente')).toBeVisible()
})

test('mantém as telas novas ao navegar para auditoria e voltar', async ({ page }) => {
  await page.goto('/runs?mode=demo')
  await expect(page.getByRole('heading', { name: 'Veja o avaliador trabalhando' })).toBeVisible()

  await page.getByRole('link', { name: 'Auditoria de viés' }).click()
  await expect(page).toHaveURL(/\/bias$/)
  await expect(page.getByRole('heading', { name: 'Descubra quando o avaliador pode ser influenciado' })).toBeVisible()
  await expect(page.getByText('Comece sem chaves e sem custo')).toBeVisible()

  await page.goBack()
  await expect(page).toHaveURL(/\/runs\?mode=demo$/)
  await expect(page.getByRole('heading', { name: 'Veja o avaliador trabalhando' })).toBeVisible()
  await expect(page.getByText('Demonstração local', { exact: true })).toBeVisible()
})

test('executa exemplos locais aprovado e reprovado sem provider', async ({ page }) => {
  await page.goto('/runs?mode=demo')
  await page.getByRole('button', { name: /Executar exemplo aprovado/i }).click()
  await expect(page.getByText('Sucesso: a resposta atingiu o objetivo esperado').first()).toBeVisible()
  await expect(page.getByText(/Trace fornecido.*não gerado por IA/i).first()).toBeVisible()

  await page.getByRole('button', { name: /Executar exemplo reprovado/i }).click()
  await expect(page.getByText('Falha: a resposta não atendeu aos critérios').first()).toBeVisible()
  await expect(page.getByText('São Paulo').first()).toBeVisible()
})
