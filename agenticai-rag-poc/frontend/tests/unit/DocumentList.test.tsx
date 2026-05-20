import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import DocumentList from '@/components/DocumentList'

vi.mock('@/services/api', () => ({
  documentsApi: {
    list: vi.fn(),
    remove: vi.fn(),
    getChunks: vi.fn(),
  },
  extractErrorMessage: vi.fn((e) => String(e)),
}))

vi.mock('react-hot-toast', () => ({
  default: { error: vi.fn(), success: vi.fn() },
}))

vi.mock('@/store/authStore', () => ({
  useAuthStore: vi.fn(),
}))

vi.mock('@/components/DocumentViewerModal', () => ({
  default: ({
    filename,
    onClose,
    onUnavailable,
  }: {
    filename: string | null
    onClose: () => void
    onUnavailable?: (filename: string) => void
  }) =>
    filename ? (
      <div data-testid="viewer-modal">
        {filename}
        <button onClick={onClose}>close</button>
        <button onClick={() => onUnavailable?.(filename)}>unavailable</button>
      </div>
    ) : null,
}))

import { documentsApi, extractErrorMessage } from '@/services/api'
import toast from 'react-hot-toast'
import { useAuthStore } from '@/store/authStore'

const mockUseAuthStore = vi.mocked(useAuthStore as unknown as (selector: (s: { isGuest: boolean }) => boolean) => boolean)

const documentListResponse = (documents: string[]) => ({
  documents,
  count: documents.length,
})

function setGuest(isGuest: boolean) {
  mockUseAuthStore.mockImplementation((selector) => selector({ isGuest }))
}

describe('DocumentList', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setGuest(false)
    vi.mocked(documentsApi.list).mockResolvedValue(documentListResponse([]))
    vi.mocked(documentsApi.getChunks).mockResolvedValue({ filename: 'doc.txt', chunks: [], total_chunks: 0 })
  })

  it('shows empty state when no documents are indexed', async () => {
    vi.mocked(documentsApi.list).mockResolvedValue(documentListResponse([]))
    render(<DocumentList refreshKey={0} />)
    await waitFor(() => expect(screen.getByText(/No documents indexed yet/)).toBeTruthy())
  })

  it('shows guest-specific empty state for guest users', async () => {
    setGuest(true)
    vi.mocked(documentsApi.list).mockResolvedValue(documentListResponse([]))
    render(<DocumentList refreshKey={0} />)
    await waitFor(() => expect(screen.getByText(/No documents are indexed yet/)).toBeTruthy())
  })

  it('renders document filenames from the API response', async () => {
    vi.mocked(documentsApi.list).mockResolvedValue(documentListResponse(['report.pdf', 'data.csv']))
    render(<DocumentList refreshKey={0} />)
    await waitFor(() => expect(screen.getByText('report.pdf')).toBeTruthy())
    expect(screen.getByText('data.csv')).toBeTruthy()
  })

  it('shows document count badge', async () => {
    vi.mocked(documentsApi.list).mockResolvedValue(documentListResponse(['a.txt', 'b.txt']))
    render(<DocumentList refreshKey={0} />)
    await waitFor(() => expect(screen.getByText('2')).toBeTruthy())
  })

  it('calls onDocumentsChange with fetched documents', async () => {
    const docs = ['notes.txt']
    vi.mocked(documentsApi.list).mockResolvedValue(documentListResponse(docs))
    const onChange = vi.fn()
    render(<DocumentList refreshKey={0} onDocumentsChange={onChange} />)
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(docs))
  })

  it('re-fetches when refreshKey changes', async () => {
    vi.mocked(documentsApi.list).mockResolvedValue(documentListResponse([]))
    const { rerender } = render(<DocumentList refreshKey={0} />)
    await waitFor(() => expect(vi.mocked(documentsApi.list)).toHaveBeenCalledTimes(1))
    rerender(<DocumentList refreshKey={1} />)
    await waitFor(() => expect(vi.mocked(documentsApi.list)).toHaveBeenCalledTimes(2))
  })

  it('shows error toast when list fetch fails', async () => {
    vi.mocked(documentsApi.list).mockRejectedValue(new Error('Network error'))
    vi.mocked(extractErrorMessage).mockReturnValue('Network error')
    render(<DocumentList refreshKey={0} />)
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Network error'))
  })

  it('hides delete buttons for guest users', async () => {
    setGuest(true)
    vi.mocked(documentsApi.list).mockResolvedValue(documentListResponse(['notes.txt']))
    render(<DocumentList refreshKey={0} />)
    await waitFor(() => screen.getByText('notes.txt'))
    expect(screen.queryByLabelText('Remove notes.txt')).toBeNull()
  })

  it('shows delete button for admin users', async () => {
    vi.mocked(documentsApi.list).mockResolvedValue(documentListResponse(['notes.txt']))
    render(<DocumentList refreshKey={0} />)
    await waitFor(() => expect(screen.getByLabelText('Remove notes.txt')).toBeTruthy())
  })

  it('opens DocumentViewerModal when eye icon is clicked', async () => {
    vi.mocked(documentsApi.list).mockResolvedValue(documentListResponse(['report.pdf']))
    render(<DocumentList refreshKey={0} />)
    await waitFor(() => screen.getByLabelText('View report.pdf'))
    fireEvent.click(screen.getByLabelText('View report.pdf'))
    await waitFor(() => expect(screen.getByTestId('viewer-modal')).toBeTruthy())
    // The modal renders the filename — there may be multiple 'report.pdf' text nodes
    // (list item + modal), so verify via testid instead
    expect(screen.getByTestId('viewer-modal').textContent).toContain('report.pdf')
  })

  it('closes DocumentViewerModal on close callback', async () => {
    vi.mocked(documentsApi.list).mockResolvedValue(documentListResponse(['report.pdf']))
    render(<DocumentList refreshKey={0} />)
    await waitFor(() => fireEvent.click(screen.getByLabelText('View report.pdf')))
    await waitFor(() => screen.getByTestId('viewer-modal'))
    fireEvent.click(screen.getByText('close'))
    await waitFor(() => expect(screen.queryByTestId('viewer-modal')).toBeNull())
  })

  it('keeps admin documents listed when preview content is unavailable', async () => {
    vi.mocked(documentsApi.list).mockResolvedValue(documentListResponse(['legacy.pdf']))
    const onChange = vi.fn()
    render(<DocumentList refreshKey={0} onDocumentsChange={onChange} />)
    await waitFor(() => screen.getByLabelText('View legacy.pdf'))
    fireEvent.click(screen.getByLabelText('View legacy.pdf'))
    await waitFor(() => screen.getByText('unavailable'))
    fireEvent.click(screen.getByText('unavailable'))
    expect(screen.getByLabelText('View legacy.pdf')).toBeInTheDocument()
    expect(onChange).toHaveBeenLastCalledWith(['legacy.pdf'])
  })

  it('removes stale guest document when viewer reports it unavailable', async () => {
    setGuest(true)
    vi.mocked(documentsApi.list).mockResolvedValue(documentListResponse(['stale.txt']))
    const onChange = vi.fn()
    render(<DocumentList refreshKey={0} onDocumentsChange={onChange} />)
    await waitFor(() => screen.getByLabelText('View stale.txt'))
    fireEvent.click(screen.getByLabelText('View stale.txt'))
    await waitFor(() => screen.getByText('unavailable'))
    fireEvent.click(screen.getByText('unavailable'))
    await waitFor(() => expect(screen.queryByText('stale.txt')).not.toBeInTheDocument())
    expect(onChange).toHaveBeenLastCalledWith([])
  })

  // ── Delete confirmation dialog tests (Feature 4-D) ─────────────────────────

  it('shows inline confirmation dialog when trash icon is clicked', async () => {
    vi.mocked(documentsApi.list).mockResolvedValue(documentListResponse(['notes.txt']))
    render(<DocumentList refreshKey={0} />)
    await waitFor(() => screen.getByLabelText('Remove notes.txt'))
    fireEvent.click(screen.getByLabelText('Remove notes.txt'))
    await waitFor(() =>
      expect(screen.getByTestId('delete-confirm-btn')).toBeInTheDocument(),
    )
    expect(screen.getByTestId('delete-cancel-btn')).toBeInTheDocument()
    expect(screen.getByText(/This cannot be undone/i)).toBeInTheDocument()
  })

  it('cancel button hides confirmation dialog without deleting', async () => {
    vi.mocked(documentsApi.list).mockResolvedValue(documentListResponse(['notes.txt']))
    render(<DocumentList refreshKey={0} />)
    await waitFor(() => screen.getByLabelText('Remove notes.txt'))
    fireEvent.click(screen.getByLabelText('Remove notes.txt'))
    await waitFor(() => screen.getByTestId('delete-cancel-btn'))
    fireEvent.click(screen.getByTestId('delete-cancel-btn'))
    await waitFor(() =>
      expect(screen.queryByTestId('delete-confirm-btn')).not.toBeInTheDocument(),
    )
    expect(vi.mocked(documentsApi.remove)).not.toHaveBeenCalled()
  })

  it('confirm button calls documentsApi.remove and removes item from list', async () => {
    vi.mocked(documentsApi.list).mockResolvedValue(documentListResponse(['notes.txt']))
    vi.mocked(documentsApi.remove).mockResolvedValue({ filename: 'notes.txt', chunks_removed: 1 })
    const onChange = vi.fn()
    render(<DocumentList refreshKey={0} onDocumentsChange={onChange} />)
    await waitFor(() => screen.getByLabelText('Remove notes.txt'))
    fireEvent.click(screen.getByLabelText('Remove notes.txt'))
    await waitFor(() => screen.getByTestId('delete-confirm-btn'))
    fireEvent.click(screen.getByTestId('delete-confirm-btn'))
    await waitFor(() => expect(vi.mocked(documentsApi.remove)).toHaveBeenCalledWith('notes.txt'))
    expect(toast.success).toHaveBeenCalledWith('Removed notes.txt')
    expect(onChange).toHaveBeenLastCalledWith([])
  })

  it('shows error toast when delete fails and hides confirmation', async () => {
    vi.mocked(documentsApi.list).mockResolvedValue(documentListResponse(['notes.txt']))
    vi.mocked(documentsApi.remove).mockRejectedValue(new Error('Delete failed'))
    vi.mocked(extractErrorMessage).mockReturnValue('Delete failed')
    render(<DocumentList refreshKey={0} />)
    await waitFor(() => screen.getByLabelText('Remove notes.txt'))
    fireEvent.click(screen.getByLabelText('Remove notes.txt'))
    await waitFor(() => screen.getByTestId('delete-confirm-btn'))
    fireEvent.click(screen.getByTestId('delete-confirm-btn'))
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Delete failed'))
    await waitFor(() =>
      expect(screen.queryByTestId('delete-confirm-btn')).not.toBeInTheDocument(),
    )
  })

  it('treats delete 404 as already removed and removes stale item from list', async () => {
    vi.mocked(documentsApi.list).mockResolvedValue(documentListResponse(['stale.txt']))
    vi.mocked(documentsApi.remove).mockRejectedValue({ isAxiosError: true, response: { status: 404 } })
    const onChange = vi.fn()
    render(<DocumentList refreshKey={0} onDocumentsChange={onChange} />)
    await waitFor(() => screen.getByLabelText('Remove stale.txt'))
    fireEvent.click(screen.getByLabelText('Remove stale.txt'))
    await waitFor(() => screen.getByTestId('delete-confirm-btn'))
    fireEvent.click(screen.getByTestId('delete-confirm-btn'))
    await waitFor(() => expect(screen.queryByText('stale.txt')).not.toBeInTheDocument())
    expect(toast.success).toHaveBeenCalledWith('stale.txt was already removed')
    expect(onChange).toHaveBeenLastCalledWith([])
  })

  it('clicking trash on second doc replaces pending confirmation from first', async () => {
    vi.mocked(documentsApi.list).mockResolvedValue(documentListResponse(['first.pdf', 'second.txt']))
    render(<DocumentList refreshKey={0} />)
    await waitFor(() => screen.getByLabelText('Remove first.pdf'))
    // Open confirm for first doc
    fireEvent.click(screen.getByLabelText('Remove first.pdf'))
    await waitFor(() => screen.getByTestId('delete-confirm-btn'))
    // Click trash for second doc
    fireEvent.click(screen.getByLabelText('Remove second.txt'))
    await waitFor(() => {
      // Only one confirm dialog should be visible
      expect(screen.getAllByTestId('delete-confirm-btn')).toHaveLength(1)
    })
    // Should show second.txt's dialog
    expect(screen.getByText(/'second\.txt'/)).toBeInTheDocument()
  })

  it('shows only one confirmation row at a time', async () => {
    vi.mocked(documentsApi.list).mockResolvedValue(documentListResponse(['a.pdf', 'b.txt']))
    render(<DocumentList refreshKey={0} />)
    await waitFor(() => screen.getByLabelText('Remove a.pdf'))
    fireEvent.click(screen.getByLabelText('Remove a.pdf'))
    await waitFor(() => screen.getByTestId('delete-confirm-btn'))
    expect(screen.getAllByTestId('delete-confirm-btn')).toHaveLength(1)
    expect(screen.getAllByTestId('delete-cancel-btn')).toHaveLength(1)
  })
})
