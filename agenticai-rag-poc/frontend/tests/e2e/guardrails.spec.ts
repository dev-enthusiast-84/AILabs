/**
 * E2E tests for the Content Guardrails modal.
 *
 * Auth is injected via sessionStorage to avoid the login UI.
 * These tests verify the modal's behaviour in admin and guest contexts.
 * API calls are NOT mocked — the backend must be running for full coverage;
 * structural / UI-only assertions pass in isolation.
 */
import { test, expect } from '@playwright/test'

// ── Helpers ───────────────────────────────────────────────────────────────────

async function injectAdmin(page: import('@playwright/test').Page) {
  await page.goto('/login')
  await page.evaluate(() => {
    sessionStorage.setItem('auth-store', JSON.stringify({
      state: { token: 'mock-token', username: 'admin', isGuest: false, guestUploadedDocs: [], guestSettingsUsed: false },
      version: 0,
    }))
  })
  await page.goto('/')
}

async function injectGuest(page: import('@playwright/test').Page) {
  await page.goto('/login')
  await page.evaluate(() => {
    sessionStorage.setItem('auth-store', JSON.stringify({
      state: { token: 'mock-guest-token', username: 'guest', isGuest: true, guestUploadedDocs: [], guestSettingsUsed: false },
      version: 0,
    }))
  })
  await page.goto('/')
}

// ── Admin: guardrails modal structure ─────────────────────────────────────────

test.describe('Guardrails modal — admin user', () => {
  test.beforeEach(async ({ page }) => {
    await injectAdmin(page)
  })

  test('guardrails button is visible in header', async ({ page }) => {
    await expect(page.getByTestId('guardrails-btn')).toBeVisible()
  })

  test('guardrails modal opens on button click', async ({ page }) => {
    await page.getByTestId('guardrails-btn').click()
    await expect(page.getByRole('dialog')).toBeVisible()
  })

  test('modal shows Rules and Test tabs for admin', async ({ page }) => {
    await page.getByTestId('guardrails-btn').click()
    await expect(page.getByTestId('tab-rules')).toBeVisible()
    await expect(page.getByTestId('tab-test')).toBeVisible()
  })

  test('Rules tab is active by default', async ({ page }) => {
    await page.getByTestId('guardrails-btn').click()
    // Filter controls indicate the Rules tab is active
    await expect(page.getByTestId('filter-type')).toBeVisible()
  })

  test('Test tab is accessible for admin', async ({ page }) => {
    await page.getByTestId('guardrails-btn').click()
    await page.getByTestId('tab-test').click()
    await expect(page.getByTestId('test-text-input')).toBeVisible()
    await expect(page.getByTestId('run-test-btn')).toBeVisible()
  })

  test('run-test button is disabled when text input is empty', async ({ page }) => {
    await page.getByTestId('guardrails-btn').click()
    await page.getByTestId('tab-test').click()
    await expect(page.getByTestId('run-test-btn')).toBeDisabled()
  })

  test('run-test button enables once text is entered', async ({ page }) => {
    await page.getByTestId('guardrails-btn').click()
    await page.getByTestId('tab-test').click()
    await page.getByTestId('test-text-input').fill('Hello world')
    await expect(page.getByTestId('run-test-btn')).toBeEnabled()
  })

  test('add rule button is visible for admin on Rules tab', async ({ page }) => {
    await page.getByTestId('guardrails-btn').click()
    await expect(page.getByTestId('add-rule-btn')).toBeVisible()
  })

  test('add rule form opens on button click', async ({ page }) => {
    await page.getByTestId('guardrails-btn').click()
    await page.getByTestId('add-rule-btn').click()
    await expect(page.getByTestId('add-rule-form')).toBeVisible()
    await expect(page.getByTestId('add-rule-name')).toBeVisible()
  })

  test('modal closes on X button', async ({ page }) => {
    await page.getByTestId('guardrails-btn').click()
    await page.getByTestId('guardrails-close').click()
    await expect(page.getByRole('dialog')).not.toBeVisible()
  })

  test('modal closes on footer Close button', async ({ page }) => {
    await page.getByTestId('guardrails-btn').click()
    await page.getByTestId('guardrails-close-footer').click()
    await expect(page.getByRole('dialog')).not.toBeVisible()
  })

  test('modal closes on Escape key', async ({ page }) => {
    await page.getByTestId('guardrails-btn').click()
    await expect(page.getByRole('dialog')).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog')).not.toBeVisible()
  })

  test('filter selects are rendered on Rules tab', async ({ page }) => {
    await page.getByTestId('guardrails-btn').click()
    await expect(page.getByTestId('filter-type')).toBeVisible()
    await expect(page.getByTestId('filter-target')).toBeVisible()
    await expect(page.getByTestId('filter-action')).toBeVisible()
  })
})

// ── Guest: guardrails modal restrictions ─────────────────────────────────────

test.describe('Guardrails modal — guest user', () => {
  test.beforeEach(async ({ page }) => {
    await injectGuest(page)
  })

  test('guardrails button is visible for guest', async ({ page }) => {
    await expect(page.getByTestId('guardrails-btn')).toBeVisible()
  })

  test('modal opens for guest', async ({ page }) => {
    await page.getByTestId('guardrails-btn').click()
    await expect(page.getByRole('dialog')).toBeVisible()
  })

  test('Test tab is hidden for guest', async ({ page }) => {
    await page.getByTestId('guardrails-btn').click()
    await expect(page.getByTestId('tab-test')).not.toBeVisible()
  })

  test('add rule button is hidden for guest', async ({ page }) => {
    await page.getByTestId('guardrails-btn').click()
    await expect(page.getByTestId('add-rule-btn')).not.toBeVisible()
  })

  test('guest read-only notice is shown', async ({ page }) => {
    await page.getByTestId('guardrails-btn').click()
    await expect(page.getByText(/Guest mode — view only/i)).toBeVisible()
  })
})
