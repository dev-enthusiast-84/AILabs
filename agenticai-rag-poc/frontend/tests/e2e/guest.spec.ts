/**
 * E2E tests for the guest user flow.
 *
 * Covers:
 *   - Guest login UI elements
 *   - Guest mode banner and header badge
 *   - Upload dropzone restriction (TXT-only hint)
 *   - Settings modal in guest context (one-time lock)
 *
 * Auth is injected via sessionStorage injection.
 * These tests do NOT require the backend running for structural assertions.
 */
import { test, expect } from '@playwright/test'
import { injectGuest } from './helpers'

// Alias to match the call-sites below that use guestSettingsUsed option.
const injectGuestAuth = injectGuest

// ── Login page: guest entry point ─────────────────────────────────────────────

test.describe('Guest login UI', () => {
  test('Continue as Guest button is visible on the login page', async ({ page }) => {
    await page.goto('/login')
    await expect(page.getByTestId('guest-button')).toBeVisible()
  })

  test('guest button is enabled by default', async ({ page }) => {
    await page.goto('/login')
    await expect(page.getByTestId('guest-button')).toBeEnabled()
  })

  test('login page shows guest access description', async ({ page }) => {
    await page.goto('/login')
    await expect(page.getByText(/Guest access/i)).toBeVisible()
  })

  test('login page shows 15 min session note', async ({ page }) => {
    await page.goto('/login')
    await expect(page.getByText(/15 min/i)).toBeVisible()
  })
})

// ── Guest dashboard: header + banner ─────────────────────────────────────────

test.describe('Guest dashboard — header and banner', () => {
  test.beforeEach(async ({ page }) => {
    await injectGuestAuth(page)
  })

  test('guest badge is shown in the header', async ({ page }) => {
    // Scope to <header> element to avoid matching the guest info banner below it
    await expect(page.locator('header').getByText('Guest')).toBeVisible()
  })

  test('sign-in button is shown for guest', async ({ page }) => {
    await expect(page.getByTestId('signin-btn')).toBeVisible()
  })

  test('settings button is visible for guest', async ({ page }) => {
    await expect(page.getByTestId('settings-btn')).toBeVisible()
  })

  test('guardrails button is visible for guest', async ({ page }) => {
    await expect(page.getByTestId('guardrails-btn')).toBeVisible()
  })

  test('guest info banner mentions TXT file limit', async ({ page }) => {
    // Match the header guest banner specifically (starts with "Guest mode:")
    // to avoid strict-mode collision with the upload card's guest notice
    await expect(page.getByText(/Guest mode:.*1 TXT file/i)).toBeVisible()
  })

  test('guest info banner mentions 15-minute session', async ({ page }) => {
    await expect(page.getByText(/15-minute session/i)).toBeVisible()
  })

  test('guest info banner has a Sign in link', async ({ page }) => {
    await expect(page.getByRole('button', { name: /Sign in/i }).first()).toBeVisible()
  })
})

// ── Guest dashboard: upload area ──────────────────────────────────────────────

test.describe('Guest dashboard — upload area', () => {
  test.beforeEach(async ({ page }) => {
    await injectGuestAuth(page)
  })

  test('upload dropzone is visible', async ({ page }) => {
    await expect(page.getByTestId('dropzone')).toBeVisible()
  })

  test('upload area shows guest TXT-only restriction note', async ({ page }) => {
    await expect(page.getByText(/TXT only/i)).toBeVisible()
  })

  test('upload area shows 2 MB guest limit', async ({ page }) => {
    // Scope to the dropzone to avoid strict-mode collision with the header banner
    await expect(page.getByTestId('dropzone').getByText(/2 MB/i)).toBeVisible()
  })

  test('guest warning banner is shown inside upload card', async ({ page }) => {
    await expect(page.getByText(/Sign in to upload PDF/i)).toBeVisible()
  })
})

// ── Guest settings: one-time lock ─────────────────────────────────────────────

test.describe('Guest settings — one-time lock', () => {
  test('settings modal is accessible for guest (settings not yet used)', async ({ page }) => {
    await injectGuestAuth(page, { guestSettingsUsed: false })
    await page.getByTestId('settings-btn').click()
    await expect(page.getByRole('dialog')).toBeVisible()
    await expect(page.getByTestId('model-select')).toBeVisible()
  })

  test('guest settings shows one-time configuration notice when unlocked', async ({ page }) => {
    await injectGuestAuth(page, { guestSettingsUsed: false })
    await page.getByTestId('settings-btn').click()
    await expect(page.getByText(/one-time configuration/i)).toBeVisible()
  })

  test('settings are locked when guestSettingsUsed is true', async ({ page }) => {
    await injectGuestAuth(page, { guestSettingsUsed: true })
    await page.getByTestId('settings-btn').click()
    await expect(page.getByText(/Settings are locked for this session/i)).toBeVisible()
  })

  test('save button shows Locked when guest settings are used', async ({ page }) => {
    await injectGuestAuth(page, { guestSettingsUsed: true })
    await page.getByTestId('settings-btn').click()
    await expect(page.getByTestId('settings-save-btn')).toHaveText('Locked')
  })

  test('save button is disabled when guest settings are locked', async ({ page }) => {
    await injectGuestAuth(page, { guestSettingsUsed: true })
    await page.getByTestId('settings-btn').click()
    await expect(page.getByTestId('settings-save-btn')).toBeDisabled()
  })

  test('api key input is disabled when guest settings are locked', async ({ page }) => {
    await injectGuestAuth(page, { guestSettingsUsed: true })
    await page.getByTestId('settings-btn').click()
    await expect(page.getByTestId('api-key-input')).toBeDisabled()
  })

  test('model select is disabled when guest settings are locked', async ({ page }) => {
    await injectGuestAuth(page, { guestSettingsUsed: true })
    await page.getByTestId('settings-btn').click()
    await expect(page.getByTestId('model-select')).toBeDisabled()
  })

  test('settings modal closes on Cancel', async ({ page }) => {
    await injectGuestAuth(page, { guestSettingsUsed: false })
    await page.getByTestId('settings-btn').click()
    await page.getByRole('button', { name: 'Cancel' }).click()
    await expect(page.getByRole('dialog')).not.toBeVisible()
  })
})
