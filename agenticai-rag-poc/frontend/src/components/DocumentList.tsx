import { useEffect, useState } from 'react'
import axios from 'axios'
import { DocumentTextIcon, EyeIcon, TrashIcon, DocumentIcon, ArrowDownTrayIcon, SparklesIcon } from '@heroicons/react/24/outline'
import toast from 'react-hot-toast'
import { documentsApi, settingsApi, extractErrorMessage } from '@/services/api'
import { useAuthStore } from '@/store/authStore'
import DocumentViewerModal from '@/components/DocumentViewerModal'
import type { DocumentMetadataItem } from '@/types'


interface Props {
  refreshKey: number
  onDocumentsChange?: (docs: string[]) => void
}

function getFileAccentClass(filename: string): string {
  const ext = filename.split('.').pop()?.toLowerCase()
  switch (ext) {
    case 'pdf':  return 'text-rose-500'
    case 'csv':  return 'text-emerald-600'
    case 'xlsx':
    case 'xls':  return 'text-green-600'
    default:     return 'text-sky-600'
  }
}

export default function DocumentList({ refreshKey, onDocumentsChange }: Props) {
  const [documents, setDocuments] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [deleting, setDeleting] = useState<string | null>(null)
  const [pendingDelete, setPendingDelete] = useState<string | null>(null)
  const [viewing, setViewing] = useState<string | null>(null)
  const [chunkCounts, setChunkCounts] = useState<Record<string, number>>({})
  const [downloading, setDownloading] = useState<string | null>(null)
  const [metadata, setMetadata] = useState<Record<string, DocumentMetadataItem>>({})
  const [cleaning, setCleaning] = useState(false)
  const [retentionDays, setRetentionDays] = useState<number>(30)
  // T010 — guest session-pruned banner
  const [prunedCount, setPrunedCount] = useState(0)
  const [showPrunedBanner, setShowPrunedBanner] = useState(false)
  // T025 — admin near-limit banner
  const [showNearLimitBanner, setShowNearLimitBanner] = useState(false)
  const [adminDocCount, setAdminDocCount] = useState(0)
  const [adminDocLimit, setAdminDocLimit] = useState(100)
  const isGuest = useAuthStore((s) => s.isGuest)

  const removeDocumentFromState = (filename: string) => {
    setDocuments((prev) => {
      const updated = prev.filter((d) => d !== filename)
      onDocumentsChange?.(updated)
      return updated
    })
  }

  const handleCleanup = async () => {
    setCleaning(true)
    try {
      const result = await documentsApi.triggerCleanup(false)
      if (result.deleted_count === 0) {
        toast.success('No stale or expired documents found.')
      } else {
        toast.success(`Removed ${result.deleted_count} document${result.deleted_count !== 1 ? 's' : ''}: ${result.deleted_sources.join(', ')}`)
        result.deleted_sources.forEach((name: string) => removeDocumentFromState(name))
      }
    } catch (err) {
      toast.error(extractErrorMessage(err))
    } finally {
      setCleaning(false)
    }
  }

  useEffect(() => {
    if (!isGuest) {
      settingsApi.get().then((s) => setRetentionDays(s.admin_doc_retention_days ?? 30)).catch(() => {})
    }
  }, [isGuest])

  // T010 — auto-dismiss guest session-pruned banner after 5 s
  useEffect(() => {
    if (prunedCount > 0) {
      setShowPrunedBanner(true)
      const timer = setTimeout(() => setShowPrunedBanner(false), 5000)
      return () => clearTimeout(timer)
    }
  }, [prunedCount])

  // T025 — admin near-limit banner (persistent, dismissible via sessionStorage)
  useEffect(() => {
    if (isGuest) return
    const dismissed = sessionStorage.getItem('doc_limit_banner_dismissed')
    if (dismissed) return
    settingsApi.get().then((s) => {
      if (s.admin_docs_near_limit) {
        setAdminDocCount(s.admin_doc_count ?? 0)
        setAdminDocLimit(s.admin_doc_limit ?? 100)
        setShowNearLimitBanner(true)
      }
    }).catch(() => {})
  }, [isGuest])

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      try {
        const data = await documentsApi.list()
        setDocuments(data.documents)
        onDocumentsChange?.(data.documents)
        setPrunedCount(data.pruned_previous_session_count ?? 0)
        const counts: Record<string, number> = {}
        await Promise.allSettled(
          data.documents.map((doc) =>
            documentsApi.getChunks(doc).then((r) => { counts[doc] = r.total_chunks })
          )
        )
        setChunkCounts(counts)

        // Enrich with metadata for admin users only
        if (!isGuest) {
          try {
            const meta = await documentsApi.getMetadata()
            const metaMap: Record<string, DocumentMetadataItem> = {}
            for (const item of meta.documents) {
              metaMap[item.filename] = item
            }
            setMetadata(metaMap)
          } catch {
            // Fall back gracefully — metadata enrichment is optional
          }
        }
      } catch (err) {
        toast.error(extractErrorMessage(err))
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [refreshKey, onDocumentsChange, isGuest])

  const handleDelete = async (filename: string) => {
    setDeleting(filename)
    try {
      await documentsApi.remove(filename)
      toast.success(`Removed ${filename}`)
      setPendingDelete(null)
      removeDocumentFromState(filename)
    } catch (err) {
      if (axios.isAxiosError(err) && err.response?.status === 404) {
        toast.success(`${filename} was already removed`)
        removeDocumentFromState(filename)
      } else {
        toast.error(extractErrorMessage(err))
      }
      setPendingDelete(null)
    } finally {
      setDeleting(null)
    }
  }

  const handleDownload = async (filename: string) => {
    setDownloading(filename)
    try {
      const blob = await documentsApi.getFile(filename)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      toast.error(extractErrorMessage(err))
    } finally {
      setDownloading(null)
    }
  }

  if (loading) {
    return (
      <div className="card p-5">
        <div className="flex items-center gap-3">
          <div className="w-4 h-4 rounded-full border-2 border-sky-500 border-t-transparent animate-spin" />
          <p className="text-sm text-slate-400">Loading documents…</p>
        </div>
      </div>
    )
  }

  return (
    <>
      <div className="card p-5">
        {/* T010 — Guest session-pruned info banner */}
        {showPrunedBanner && isGuest && (
          <div className="mb-3 rounded-md bg-blue-50 border border-blue-200 p-3 text-sm text-blue-700 flex items-center justify-between">
            <span>Previous session documents have been cleared.</span>
            <button onClick={() => setShowPrunedBanner(false)} className="ml-2 text-blue-500 hover:text-blue-700">✕</button>
          </div>
        )}

        {/* T025 — Admin near-limit amber banner */}
        {showNearLimitBanner && !isGuest && (
          <div className="mb-3 rounded-md bg-amber-50 border border-amber-200 p-3 text-sm text-amber-700 flex items-center justify-between">
            <span>You have {adminDocCount}/{adminDocLimit} documents indexed. Consider running cleanup.</span>
            <div className="flex items-center gap-2">
              <a href="#document-retention" className="underline">Go to Settings →</a>
              <button onClick={() => { sessionStorage.setItem('doc_limit_banner_dismissed', '1'); setShowNearLimitBanner(false) }} className="text-amber-500 hover:text-amber-700">✕</button>
            </div>
          </div>
        )}

        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-semibold text-slate-900 flex items-center gap-2">
            Indexed Documents
            <span className="text-xs font-normal text-slate-500 bg-slate-100 border border-slate-200 px-2 py-0.5 rounded-full">
              {documents.length}
            </span>
          </h2>
          {!isGuest && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-400">Auto-cleanup: {retentionDays}d</span>
              <button
                type="button"
                onClick={() => void handleCleanup()}
                disabled={cleaning}
                title={`Remove stale and documents older than ${retentionDays} days`}
                className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-lg border border-slate-200 text-slate-600 hover:border-amber-300 hover:text-amber-700 hover:bg-amber-50 transition-colors disabled:opacity-50"
                data-testid="cleanup-btn"
              >
                {cleaning ? (
                  <div className="h-3 w-3 rounded-full border border-slate-400 border-t-transparent animate-spin" />
                ) : (
                  <SparklesIcon className="h-3 w-3" />
                )}
                {cleaning ? 'Cleaning…' : 'Clean up'}
              </button>
            </div>
          )}
        </div>
        {documents.length === 0 ? (
          <div className="py-6 text-center">
            <DocumentIcon className="h-8 w-8 text-slate-300 mx-auto mb-2" />
            <p className="text-sm text-slate-400">
              {isGuest ? 'No documents are indexed yet.' : 'No documents indexed yet. Upload one above.'}
            </p>
          </div>
        ) : (
          <ul className="divide-y divide-slate-100 -mx-1">
            {documents.map((doc) => (
              <li key={doc}>
                <div className="flex items-center justify-between py-2.5 px-1 rounded-lg hover:bg-slate-50 transition-colors group">
                  <div className="flex items-center gap-2.5 min-w-0">
                    <DocumentTextIcon className={`h-4 w-4 shrink-0 ${getFileAccentClass(doc)}`} />
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="text-sm text-slate-600 truncate group-hover:text-slate-900 transition-colors">{doc}</span>
                        {!isGuest && metadata[doc]?.availability === 'stale' && (
                          <span
                            className="inline-flex items-center rounded-full bg-amber-100 px-1.5 py-0.5 text-xs font-medium text-amber-800"
                            title="No chunks found in the vector index. Re-upload to restore."
                            data-testid={`stale-badge-${doc}`}
                          >
                            Stale
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2 flex-wrap">
                        {chunkCounts[doc] !== undefined && (
                          <span className="text-xs text-slate-400" data-testid={`chunk-count-${doc}`}>
                            {chunkCounts[doc]} chunk{chunkCounts[doc] !== 1 ? 's' : ''}
                          </span>
                        )}
                        {!isGuest && metadata[doc]?.uploaded_at && (
                          <span className="text-xs text-slate-500" data-testid={`upload-date-${doc}`}>
                            {new Date(parseInt(metadata[doc].uploaded_at!, 10) * 1000).toLocaleDateString()}
                          </span>
                        )}
                        {!isGuest && metadata[doc]?.owner_username && (
                          <span className="text-xs text-slate-400" data-testid={`owner-${doc}`}>
                            {metadata[doc].owner_username}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-1 ml-3 shrink-0">
                    {!isGuest && (
                      <button
                        onClick={() => handleDownload(doc)}
                        disabled={downloading === doc}
                        className="p-1 rounded text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 transition-colors disabled:opacity-40"
                        aria-label={`Download ${doc}`}
                        title="Download original file"
                        data-testid={`download-btn-${doc}`}
                      >
                        <ArrowDownTrayIcon className="h-4 w-4" />
                      </button>
                    )}
                    <button
                      onClick={() => setViewing(doc)}
                      className="p-1 rounded text-slate-400 hover:text-sky-600 hover:bg-sky-50 transition-colors"
                      aria-label={`View ${doc}`}
                      title="View document content"
                    >
                      <EyeIcon className="h-4 w-4" />
                    </button>
                    {!isGuest && (
                      <button
                        onClick={() => setPendingDelete(pendingDelete === doc ? null : doc)}
                        disabled={deleting === doc}
                        className="p-1 rounded text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-colors disabled:opacity-40"
                        aria-label={`Remove ${doc}`}
                      >
                        <TrashIcon className="h-4 w-4" />
                      </button>
                    )}
                  </div>
                </div>
                {/* Inline delete confirmation row */}
                {pendingDelete === doc && (
                  <div className="mx-1 mb-2 px-3 py-2 bg-rose-50 border border-rose-200 rounded-lg flex items-center justify-between gap-3">
                    <p className="text-xs text-rose-700 min-w-0">
                      Delete <span className="font-medium truncate">'{doc}'</span>? This cannot be undone.
                    </p>
                    <div className="flex items-center gap-2 shrink-0">
                      <button
                        data-testid="delete-cancel-btn"
                        onClick={() => setPendingDelete(null)}
                        disabled={deleting === doc}
                        className="px-2.5 py-1 text-xs font-medium rounded-md bg-white border border-slate-200 text-slate-600 hover:bg-slate-50 transition-colors disabled:opacity-40"
                      >
                        Cancel
                      </button>
                      <button
                        data-testid="delete-confirm-btn"
                        onClick={() => handleDelete(doc)}
                        disabled={deleting === doc}
                        className="px-2.5 py-1 text-xs font-medium rounded-md bg-rose-600 text-white hover:bg-rose-700 transition-colors disabled:opacity-50 flex items-center gap-1"
                      >
                        {deleting === doc ? (
                          <>
                            <div className="w-3 h-3 rounded-full border-2 border-white border-t-transparent animate-spin" />
                            Deleting…
                          </>
                        ) : (
                          'Confirm'
                        )}
                      </button>
                    </div>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      <DocumentViewerModal
        filename={viewing}
        onClose={() => setViewing(null)}
        onUnavailable={
          isGuest
            ? (filename) => {
                removeDocumentFromState(filename)
                setViewing(null)
              }
            : undefined
        }
      />
    </>
  )
}
