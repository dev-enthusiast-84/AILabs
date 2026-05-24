import axios from 'axios'
import { useEffect, useMemo, useState } from 'react'
import { XMarkIcon, DocumentTextIcon, TableCellsIcon, ArrowDownTrayIcon } from '@heroicons/react/24/outline'
import { documentsApi, extractErrorMessage } from '@/services/api'
import { useAuthStore } from '@/store/authStore'

interface Props {
  filename: string | null
  onClose: () => void
  onUnavailable?: (filename: string) => void
}

function fileType(filename: string): 'pdf' | 'csv' | 'excel' | 'text' {
  const ext = filename.split('.').pop()?.toLowerCase() ?? ''
  if (ext === 'pdf') return 'pdf'
  if (ext === 'csv') return 'csv'
  if (ext === 'xlsx' || ext === 'xls') return 'excel'
  return 'text'
}

export default function DocumentViewerModal({ filename, onClose, onUnavailable }: Props) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null)
  const [textContent, setTextContent] = useState<string | null>(null)
  const [apiWordCount, setApiWordCount] = useState<number | null>(null)
  const [unavailable, setUnavailable] = useState(false)
  const [contentError, setContentError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const isGuest = useAuthStore((s) => s.isGuest)
  const [activeTab, setActiveTab] = useState<'content' | 'chunks'>('content')
  const [chunks, setChunks] = useState<string[] | null>(null)
  const [chunksLoading, setChunksLoading] = useState(false)
  const [chunksError, setChunksError] = useState<string | null>(null)

  // Revoke blob URL when a new one is created or component unmounts
  useEffect(() => {
    return () => { if (blobUrl) URL.revokeObjectURL(blobUrl) }
  }, [blobUrl])

  useEffect(() => {
    if (!filename) return
    setBlobUrl(null)
    setTextContent(null)
    setApiWordCount(null)
    setUnavailable(false)
    setContentError(null)
    setLoading(true)
    setActiveTab('content')
    setChunks(null)
    setChunksError(null)

    const type = fileType(filename)

    documentsApi.getFile(filename)
      .then(async (blob) => {
        if (type === 'pdf' || type === 'excel') {
          setBlobUrl(URL.createObjectURL(blob))
        } else {
          setTextContent(await blob.text())
        }
      })
      .catch(async (err) => {
        if (axios.isAxiosError(err) && err.response?.status === 404) {
          // Fall back to chunk-stitched text for documents uploaded before file storage was added
          try {
            const data = await documentsApi.getContent(filename)
            setTextContent(data.content)
            setApiWordCount(data.word_count)
          } catch {
            setUnavailable(true)
            onUnavailable?.(filename)
          }
        } else {
          setContentError(extractErrorMessage(err))
        }
      })
      .finally(() => setLoading(false))
  }, [filename])

  useEffect(() => {
    if (!filename) return
    const handler = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [filename, onClose])

  const wordCount = useMemo(
    () => apiWordCount ?? (textContent?.trim() ? textContent.trim().split(/\s+/).filter(Boolean).length : 0),
    [apiWordCount, textContent],
  )

  const loadChunks = async () => {
    if (!filename || chunks !== null) return
    setChunksLoading(true)
    setChunksError(null)
    try {
      const data = await documentsApi.getChunks(filename)
      setChunks(data.chunks)
    } catch (err) {
      setChunksError(extractErrorMessage(err))
      setChunks([])
    } finally {
      setChunksLoading(false)
    }
  }

  if (!filename) return null

  const type = fileType(filename)
  const isTabular = type === 'csv' || type === 'excel'
  const Icon = isTabular ? TableCellsIcon : DocumentTextIcon

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm p-4"
      onClick={(e) => e.target === e.currentTarget && onClose()}
      role="dialog"
      aria-modal="true"
      aria-labelledby="doc-viewer-title"
    >
      <div className="bg-white border border-slate-200 rounded-2xl shadow-xl shadow-slate-300/40 w-full max-w-3xl max-h-[85vh] flex flex-col overflow-hidden">

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 shrink-0">
          <div className="flex items-center gap-2 min-w-0">
            <Icon className="h-5 w-5 text-sky-600 shrink-0" />
            <h2 id="doc-viewer-title" className="text-base font-semibold text-slate-900 truncate">
              {filename}
            </h2>
            {!loading && textContent && (
              <span className="ml-1 text-xs text-slate-400 font-normal shrink-0">
                — {wordCount.toLocaleString()} words
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            className="ml-4 text-slate-400 hover:text-slate-700 transition-colors shrink-0"
            aria-label="Close document viewer"
          >
            <XMarkIcon className="h-5 w-5" />
          </button>
        </div>

        {/* Tab bar — admin only */}
        {!isGuest && (
          <div className="flex border-b border-slate-200 shrink-0 px-6" role="tablist">
            <button
              role="tab"
              aria-selected={activeTab === 'content'}
              onClick={() => setActiveTab('content')}
              className={`py-2.5 px-1 mr-4 text-sm font-medium border-b-2 transition-colors ${
                activeTab === 'content'
                  ? 'border-sky-500 text-sky-600'
                  : 'border-transparent text-slate-400 hover:text-slate-700'
              }`}
              data-testid="tab-content"
            >
              Content
            </button>
            <button
              role="tab"
              aria-selected={activeTab === 'chunks'}
              onClick={() => { setActiveTab('chunks'); loadChunks() }}
              className={`py-2.5 px-1 text-sm font-medium border-b-2 transition-colors ${
                activeTab === 'chunks'
                  ? 'border-sky-500 text-sky-600'
                  : 'border-transparent text-slate-400 hover:text-slate-700'
              }`}
              data-testid="tab-chunks"
            >
              Chunks
            </button>
          </div>
        )}

        {/* Body */}
        <div className="flex-1 overflow-hidden flex flex-col">
          {activeTab === 'content' && (
            <div className="flex-1 overflow-hidden flex flex-col">
              {loading ? (
                <div className="flex items-center justify-center gap-3 py-10">
                  <div className="w-4 h-4 rounded-full border-2 border-sky-500 border-t-transparent animate-spin" />
                  <p className="text-sm text-slate-400">Loading document…</p>
                </div>
              ) : type === 'pdf' && blobUrl ? (
                <iframe
                  src={blobUrl}
                  title={filename}
                  className="flex-1 w-full border-0"
                  style={{ minHeight: '60vh' }}
                />
              ) : type === 'excel' && blobUrl ? (
                <div className="flex flex-col items-center justify-center flex-1 gap-4 py-10">
                  <p className="text-sm text-slate-500">Excel files cannot be previewed in the browser.</p>
                  <a
                    href={blobUrl}
                    download={filename}
                    className="btn-secondary flex items-center gap-2 text-sm py-2 px-4"
                  >
                    <ArrowDownTrayIcon className="h-4 w-4" />
                    Download {filename}
                  </a>
                </div>
              ) : unavailable ? (
                <div className="flex flex-col items-center justify-center flex-1 gap-2 py-10 px-6 text-center">
                  <p className="text-sm font-medium text-slate-600">Document preview is no longer available.</p>
                  <p className="text-xs text-slate-400">Re-upload the file to restore the original-file preview.</p>
                </div>
              ) : contentError ? (
                <div className="flex flex-col items-center justify-center flex-1 gap-2 py-10 px-6 text-center">
                  <p className="text-sm font-medium text-rose-600">{contentError}</p>
                </div>
              ) : textContent !== null && !textContent.trim() ? (
                <p className="text-sm text-slate-400 text-center py-10">No content found.</p>
              ) : textContent !== null ? (
                <div className="flex-1 overflow-y-auto px-6 py-5">
                  {type === 'csv' ? (
                    <pre className="text-xs font-mono text-slate-600 whitespace-pre leading-relaxed overflow-x-auto">
                      {textContent}
                    </pre>
                  ) : (
                    <div className="text-sm text-slate-700 leading-relaxed whitespace-pre-wrap font-sans">
                      {textContent}
                    </div>
                  )}
                </div>
              ) : (
                <p className="text-sm text-slate-400 text-center py-10">No content found.</p>
              )}
            </div>
          )}
          {activeTab === 'chunks' && (
            <div className="flex-1 overflow-y-auto px-6 py-5 space-y-3">
              {chunksLoading ? (
                <div className="flex items-center gap-3 py-10 justify-center">
                  <div className="w-4 h-4 rounded-full border-2 border-sky-500 border-t-transparent animate-spin" />
                  <p className="text-sm text-slate-400">Loading chunks…</p>
                </div>
              ) : chunks && chunks.length > 0 ? (
                chunks.map((chunk, i) => (
                  <div key={i} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                    <div className="text-xs font-mono text-slate-400 mb-1.5">Chunk {i + 1} of {chunks.length}</div>
                    <p className="text-sm text-slate-700 whitespace-pre-wrap leading-relaxed">{chunk}</p>
                  </div>
                ))
              ) : chunksError ? (
                <p className="text-sm text-rose-600 text-center py-10">{chunksError}</p>
              ) : (
                <p className="text-sm text-slate-400 text-center py-10">No chunks found.</p>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-slate-200 bg-slate-50 shrink-0 flex justify-between items-center">
          <p className="text-xs text-slate-400">
            Original uploaded file
          </p>
          <button onClick={onClose} className="btn-secondary text-sm py-1.5">
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
