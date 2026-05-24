/**
 * Shared Playwright auth-injection helpers.
 *
 * Uses page.addInitScript() + a single page.goto('/') instead of the
 * previous pattern of goto('/login') → evaluate() → goto('/').
 * addInitScript runs before the page's own JS, so the auth-store key is
 * already in sessionStorage when React initialises — saving one full
 * navigation per test.
 */
import type { Page } from '@playwright/test'

const _ADMIN_AUTH = {
  state: {
    token: 'mock-token',
    username: 'admin',
    isGuest: false,
    guestUploadedDocs: [],
    guestSettingsUsed: false,
  },
  version: 0,
}

const _guestAuth = (guestSettingsUsed = false) => ({
  state: {
    token: 'mock-guest-token',
    username: 'guest',
    isGuest: true,
    guestUploadedDocs: [],
    guestSettingsUsed,
  },
  version: 0,
})

/** Inject admin credentials and navigate to the dashboard in one page load. */
export async function injectAdmin(page: Page): Promise<void> {
  await page.addInitScript((auth) => {
    sessionStorage.setItem('auth-store', JSON.stringify(auth))
  }, _ADMIN_AUTH)
  await page.goto('/')
}

/** Inject guest credentials and navigate to the dashboard in one page load. */
export async function injectGuest(
  page: Page,
  { guestSettingsUsed = false }: { guestSettingsUsed?: boolean } = {},
): Promise<void> {
  await page.addInitScript((auth) => {
    sessionStorage.setItem('auth-store', JSON.stringify(auth))
  }, _guestAuth(guestSettingsUsed))
  await page.goto('/')
}
