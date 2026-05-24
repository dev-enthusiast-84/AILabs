import { useCallback, useState } from 'react'
import Header from '@/components/Header'
import DocumentUpload from '@/components/DocumentUpload'
import DocumentList from '@/components/DocumentList'
import ChatInterface from '@/components/ChatInterface'

export default function DashboardPage() {
  const [refreshKey, setRefreshKey] = useState(0)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [settingsPrerequisiteNotice, setSettingsPrerequisiteNotice] = useState<string | null>(null)
  // Lifted documents state — shared between DocumentList and ChatInterface
  // so ChatInterface can show context-based query suggestions without a second fetch.
  const [documents, setDocuments] = useState<string[]>([])
  const handleDocumentsChange = useCallback((docs: string[]) => setDocuments(docs), [])
  const openSettingsForPrerequisite = useCallback((notice: string) => {
    setSettingsPrerequisiteNotice(notice)
    setSettingsOpen(true)
  }, [])

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      <Header
        settingsOpen={settingsOpen}
        onSettingsOpenChange={setSettingsOpen}
        settingsPrerequisiteNotice={settingsPrerequisiteNotice}
        onSettingsPrerequisiteNoticeChange={setSettingsPrerequisiteNotice}
      />
      <main className="flex-1 max-w-7xl mx-auto w-full px-4 sm:px-6 py-6 sm:py-8">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 sm:gap-6">
          {/* Left panel: upload + doc list */}
          <div className="lg:col-span-1 space-y-4 sm:space-y-6">
            <DocumentUpload
              onUploaded={() => setRefreshKey((k) => k + 1)}
              onOpenSettings={openSettingsForPrerequisite}
            />
            <DocumentList
              refreshKey={refreshKey}
              onDocumentsChange={handleDocumentsChange}
            />
          </div>
          {/* Right panel: chat */}
          <div className="lg:col-span-2">
            <ChatInterface documents={documents} onOpenSettings={openSettingsForPrerequisite} />
          </div>
        </div>
      </main>
      <footer className="text-center py-4 text-xs text-slate-400 border-t border-slate-200">
        Agentic RAG — Powered by LangGraph + OpenAI
      </footer>
    </div>
  )
}
