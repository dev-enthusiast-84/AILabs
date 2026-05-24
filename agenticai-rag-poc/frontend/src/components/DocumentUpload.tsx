import { useCallback, useEffect, useState } from 'react'
import axios from 'axios'
import toast from 'react-hot-toast'
import { useDropzone } from 'react-dropzone'
import { CloudArrowUpIcon, XCircleIcon, ArrowUpTrayIcon, CheckCircleIcon } from '@heroicons/react/24/outline'
import { documentsApi, settingsApi, extractErrorMessage } from '@/services/api'
import { useAuthStore } from '@/store/authStore'

declare const __IS_VERCEL__: boolean

const ACCEPTED_ADMIN = {
  'application/pdf': ['.pdf'],
  'text/plain': ['.txt'],
  'text/csv': ['.csv'],
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
  'application/vnd.ms-excel': ['.xls'],
}

const ACCEPTED_GUEST = {
  'text/plain': ['.txt'],
}

// Vercel serverless body limit is ~4.5 MB; cap admin uploads at 4 MB when deployed there.
const MAX_SIZE_ADMIN = (__IS_VERCEL__ ? 4 : 20) * 1024 * 1024

interface Props {
  onUploaded: () => void
  onOpenSettings?: (notice: string) => void
}

type UploadResult = {
  filename: string
  status: 'pending' | 'success' | 'error'
  message: string
}

export default function DocumentUpload({ onUploaded, onOpenSettings }: Props) {
  const [uploading, setUploading] = useState(false)
  const [uploadResults, setUploadResults] = useState<UploadResult[]>([])
  const [settingsMaxUploadMb, setSettingsMaxUploadMb] = useState<number | undefined>(undefined)
  const [settingsGuestMaxUploadMb, setSettingsGuestMaxUploadMb] = useState<number | undefined>(undefined)
  const [settingsGuestMaxDocs, setSettingsGuestMaxDocs] = useState<number | undefined>(undefined)
  const { isGuest, addGuestUploadedDoc } = useAuthStore()

  useEffect(() => {
    settingsApi.get().then((s) => {
      setSettingsMaxUploadMb(s.max_upload_size_mb)
      setSettingsGuestMaxUploadMb(s.guest_max_upload_size_mb)
      setSettingsGuestMaxDocs(s.guest_max_indexed_documents)
    }).catch(() => {
      // Silently keep defaults if settings fetch fails
    })
  }, [])

  const guestMaxUploadMb = settingsGuestMaxUploadMb ?? 3
  const guestMaxDocs = settingsGuestMaxDocs ?? 1
  const adminLimitMb = settingsMaxUploadMb ?? (__IS_VERCEL__ ? 4 : 20)

  const accept  = isGuest ? ACCEPTED_GUEST : ACCEPTED_ADMIN
  const maxSize = isGuest ? guestMaxUploadMb * 1024 * 1024 : MAX_SIZE_ADMIN

  const onDrop = useCallback(
    async (accepted: File[]) => {
      if (!accepted.length) return
      const pendingResults = accepted.map((file) => ({
        filename: file.name,
        status: 'pending' as const,
        message: 'Waiting to upload...',
      }))
      setUploadResults(pendingResults)

      // Cumulative size guard: the limit applies to the whole batch, not each file.
      const totalBytes = accepted.reduce((sum, f) => sum + f.size, 0)
      if (totalBytes > maxSize) {
        const totalMb = (totalBytes / 1024 / 1024).toFixed(1)
        const limitMb = isGuest ? guestMaxUploadMb : adminLimitMb
        setUploadResults(accepted.map((file) => ({
          filename: file.name,
          status: 'error' as const,
          message: `Total batch size ${totalMb} MB exceeds the ${limitMb} MB limit. Choose fewer or smaller files.`,
        })))
        return
      }

      const failAll = (message: string) => {
        setUploadResults(pendingResults.map((result) => ({
          ...result,
          status: 'error' as const,
          message,
        })))
      }

      // Check API key is configured before attempting upload (embeddings are called during indexing)
      try {
        const s = await settingsApi.get()
        if (s.api_key_source === 'not_configured') {
          const message = 'OpenAI API key is required before uploading because document indexing creates embeddings.'
          failAll(message)
          onOpenSettings?.(message)
          return
        }
        if (s.vector_store_type === 'pinecone' && s.pinecone_api_key_source === 'not_configured') {
          const message = 'Pinecone API key is required before uploading because this deployment stores indexed chunks in Pinecone.'
          failAll(message)
          onOpenSettings?.(message)
          return
        }
        if ((s.vector_store_type === 'blob' || s.file_store_type === 'blob') && s.blob_read_write_token_source === 'not_configured') {
          const message = 'Blob read/write token is required before uploading because this deployment stores files or chunks in Blob storage.'
          failAll(message)
          onOpenSettings?.(message)
          return
        }
      } catch {
        // If settings fetch fails, let the upload proceed and surface the error naturally
      }

      setUploading(true)
      for (const file of accepted) {
        try {
          const result = await documentsApi.upload(file)
          const message = `${result.chunks_indexed} chunk${result.chunks_indexed === 1 ? '' : 's'} indexed`
          setUploadResults((current) => current.map((item) => (
            item.filename === file.name
              ? { filename: result.filename, status: 'success', message }
              : item
          )))
          if (isGuest) addGuestUploadedDoc(result.filename)
          // One-time session suggestion to run Ragas evaluation
          if (!sessionStorage.getItem('ragas_suggest_shown')) {
            sessionStorage.setItem('ragas_suggest_shown', '1')
            window.setTimeout(() => {
              toast('Tip: run Ragas evaluation to benchmark retrieval quality.', { icon: '📊' })
            }, 1500)
          }
        } catch (err) {
          let message: string
          if (axios.isAxiosError(err) && err.response?.status === 429) {
            message = 'Upload limit reached. Please wait a minute before trying again.'
          } else {
            message = extractErrorMessage(err)
          }
          setUploadResults((current) => current.map((item) => (
            item.filename === file.name
              ? { ...item, status: 'error', message }
              : item
          )))
        }
      }
      setUploading(false)
      onUploaded()
    },
    [onUploaded, onOpenSettings, isGuest, addGuestUploadedDoc, maxSize, guestMaxUploadMb, adminLimitMb],
  )

  const { getRootProps, getInputProps, isDragActive, fileRejections } = useDropzone({
    onDrop,
    accept,
    maxSize,
    multiple: !isGuest,
    maxFiles: isGuest ? guestMaxDocs : undefined,
    disabled: uploading,
  })

  const formatNote = isGuest
    ? `TXT only — up to ${guestMaxUploadMb} MB (guest limit)`
    : `PDF, TXT, CSV, XLSX — up to ${adminLimitMb} MB total`

  return (
    <div className="card p-5">
      <h2 className="text-base font-semibold text-slate-900 mb-4">Upload Documents</h2>
      <div
        {...getRootProps()}
        data-testid="dropzone"
        className={[
          'relative border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all duration-200 group',
          isDragActive
            ? 'border-sky-500 bg-sky-50 shadow-glow-sky'
            : 'border-slate-300 hover:border-sky-400 hover:bg-sky-50/50',
          uploading ? 'opacity-50 cursor-not-allowed' : '',
        ].join(' ')}
      >
        <input {...getInputProps()} data-testid="file-input" />
        <div className={[
          'w-12 h-12 rounded-xl mx-auto mb-3 flex items-center justify-center transition-all duration-200',
          isDragActive ? 'bg-sky-100 scale-110' : 'bg-slate-100 group-hover:bg-sky-50',
        ].join(' ')}>
          {uploading ? (
            <ArrowUpTrayIcon className="h-6 w-6 text-sky-600 animate-bounce" />
          ) : (
            <CloudArrowUpIcon className={`h-6 w-6 transition-colors ${isDragActive ? 'text-sky-600' : 'text-slate-400 group-hover:text-sky-600'}`} />
          )}
        </div>
        {uploading ? (
          <p className="text-sm text-sky-600 font-medium">Uploading and indexing…</p>
        ) : isDragActive ? (
          <p className="text-sm text-sky-600 font-medium">Drop {isGuest ? 'file' : 'files'} here</p>
        ) : (
          <>
            <p className="text-sm text-slate-700 font-medium">
              Drag &amp; drop {isGuest ? 'a file' : 'files'} here, or{' '}
              <span className="text-sky-600">browse</span>
            </p>
            <p className="text-xs text-slate-400 mt-1">{formatNote}</p>
          </>
        )}
      </div>
      {fileRejections.length > 0 && (
        <ul className="mt-2 space-y-1">
          {fileRejections.map(({ file, errors }) => (
            <li key={file.name} className="flex items-center gap-1.5 text-xs text-rose-600">
              <XCircleIcon className="h-4 w-4 shrink-0" />
              {file.name}: {errors.map((e) => e.message).join(', ')}
            </li>
          ))}
        </ul>
      )}
      {uploadResults.length > 0 && (
        <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50/80 overflow-hidden" aria-live="polite">
          <ul className="divide-y divide-slate-200">
            {uploadResults.map((result) => (
              <li
                key={result.filename}
                className="flex items-start gap-2 px-3 py-2 text-xs"
                data-testid={`upload-result-${result.filename}`}
              >
                {result.status === 'success' ? (
                  <CheckCircleIcon className="h-4 w-4 shrink-0 text-emerald-600 mt-0.5" />
                ) : result.status === 'error' ? (
                  <XCircleIcon className="h-4 w-4 shrink-0 text-rose-600 mt-0.5" />
                ) : (
                  <ArrowUpTrayIcon className="h-4 w-4 shrink-0 text-sky-600 mt-0.5 animate-bounce" />
                )}
                <div className="min-w-0">
                  <p className={[
                    'font-medium truncate',
                    result.status === 'success'
                      ? 'text-emerald-700'
                      : result.status === 'error'
                        ? 'text-rose-700'
                        : 'text-sky-700',
                  ].join(' ')}>
                    {result.status === 'success' ? 'Upload complete' : result.status === 'error' ? 'Upload failed' : 'Uploading'}
                    <span className="text-slate-500 font-normal"> · {result.filename}</span>
                  </p>
                  <p className="text-slate-500 break-words">{result.message}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
