/// <reference types="vite/client" />

declare const __IS_VERCEL__: boolean

interface ImportMetaEnv {
  readonly VITE_ENABLE_VERCEL_OBSERVABILITY?: string
}
