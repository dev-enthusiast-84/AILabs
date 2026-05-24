import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

/** Decode the JWT payload to read the `exp` claim (no signature verification). */
export function getTokenExpiry(token: string): Date | null {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]))
    return typeof payload.exp === 'number' ? new Date(payload.exp * 1000) : null
  } catch {
    return null
  }
}

interface AuthState {
  token: string | null
  username: string | null
  isGuest: boolean
  /** Filenames uploaded during the current guest session — cleared on login/logout. */
  guestUploadedDocs: string[]
  /** True once the guest has made their one-time settings save (both key + model locked). */
  guestSettingsUsed: boolean
  setAuth: (token: string, username: string) => void
  setGuest: (token: string) => void
  clearAuth: () => void
  isAuthenticated: () => boolean
  addGuestUploadedDoc: (filename: string) => void
  popGuestUploadedDocs: () => string[]
  markGuestSettingsUsed: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      username: null,
      isGuest: false,
      guestUploadedDocs: [],
      guestSettingsUsed: false,
      setAuth: (token, username) => {
        sessionStorage.setItem('token', token)
        set({ token, username, isGuest: false, guestUploadedDocs: [], guestSettingsUsed: false })
      },
      setGuest: (token) => {
        sessionStorage.setItem('token', token)
        set({ token, username: 'guest', isGuest: true, guestUploadedDocs: [], guestSettingsUsed: false })
      },
      clearAuth: () => {
        sessionStorage.removeItem('token')
        set({ token: null, username: null, isGuest: false, guestUploadedDocs: [], guestSettingsUsed: false })
      },
      isAuthenticated: () => {
        const token = get().token
        if (!token) return false
        const expiry = getTokenExpiry(token)
        return expiry === null || expiry > new Date()
      },
      addGuestUploadedDoc: (filename) =>
        set((s) => ({ guestUploadedDocs: [...s.guestUploadedDocs, filename] })),
      /** Return and clear the list atomically so cleanup runs exactly once. */
      popGuestUploadedDocs: () => {
        const docs = get().guestUploadedDocs
        set({ guestUploadedDocs: [] })
        return docs
      },
      markGuestSettingsUsed: () => set({ guestSettingsUsed: true }),
    }),
    {
      name: 'auth-store',
      // sessionStorage isolates each browser tab — concurrent sessions never share state.
      storage: createJSONStorage(() => sessionStorage),
      // token is excluded from the Zustand JSON blob: setAuth/setGuest/clearAuth manage
      // it directly via sessionStorage.setItem('token', …) so it is never double-stored
      // in the auth-store serialisation. onRehydrateStorage restores it into the store
      // state on page reload so isAuthenticated() and route guards work correctly.
      partialize: (s) => ({
        username: s.username,
        isGuest: s.isGuest,
        guestUploadedDocs: s.guestUploadedDocs,
        guestSettingsUsed: s.guestSettingsUsed,
      }),
      onRehydrateStorage: () => (state) => {
        if (state) {
          const stored = sessionStorage.getItem('token')
          if (stored) state.token = stored
        }
      },
    },
  ),
)
