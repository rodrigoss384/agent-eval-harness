import { expect, test } from '@playwright/test'

test('explica os quatro protocolos e executa a auditoria local', async ({ page }) => {
  await page.goto('/bias')
  await expect(page.getByRole('heading', { name: /Descubra quando o avaliador pode ser influenciado/i })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'A regra muda o resultado?' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'A ordem muda a avaliação?' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Texto longo recebe vantagem?' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'O modelo prefere sua família?' })).toBeVisible()

  await page.getByRole('button', { name: 'Executar experimento local' }).click()
  await expect(page.getByText('O resultado mudou com a regra')).toBeVisible({ timeout: 10_000 })
  await expect(page.getByText('Regra exata', { exact: true })).toBeVisible()
  await expect(page.getByText('Regra com aliases canônicos')).toBeVisible()
})
