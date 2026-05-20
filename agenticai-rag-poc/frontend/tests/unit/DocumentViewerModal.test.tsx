import { render, screen, waitFor, act } from '@testing-library/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import DocumentViewerModal from '@/components/DocumentViewerModal'

vi.mock('@/services/api', () => ({
  documentsApi: {
    getFile: vi.fn(),
    getContent: vi.fn(),
    getChunks: vi.fn(),
  },
  extractErrorMessage: vi.fn((e) => String(e)),
}))

vi.mock('@/store/authStore', () => ({
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  useAuthStore: vi.fn((selector: (s: any) => unknown) => selector({ isGuest: false })),
}))

vi.mock('react-hot-toast', () => ({ default: { error: vi.fn() } }))
vi.mock('axios', () => ({
  default: { isAxiosError: (e: unknown) => e != null && typeof e === 'object' && 'response' in e },
}))

import { documentsApi } from '@/services/api'
import { useAuthStore } from '@/store/authStore'
import toast from 'react-hot-toast'

// jsdom's Blob.prototype.text() is unreliable; use a plain object that satisfies
// the text() contract so the component's async path can be exercised.
function makeTextBlob(text: string): Blob {
  return { text: () => Promise.resolve(text) } as unknown as Blob
}

describe('DocumentViewerModal', () => {
  beforeEach(() => vi.clearAllMocks())

  it('renders null when filename is null', () => {
    const { container } = render(<DocumentViewerModal filename={null} onClose={() => {}} />)
    expect(container.firstChild).toBeNull()
  })

  it('shows loading state initially', () => {
    vi.mocked(documentsApi.getFile).mockReturnValue(new Promise(() => {}))
    render(<DocumentViewerModal filename="report.txt" onClose={() => {}} />)
    expect(screen.getByText('Loading document…')).toBeTruthy()
  })

  it('displays full text content for TXT files', async () => {
    vi.mocked(documentsApi.getFile).mockResolvedValue(makeTextBlob('Full document text here.'))
    render(<DocumentViewerModal filename="report.txt" onClose={() => {}} />)
    await waitFor(() => screen.getByText('Full document text here.'))
    expect(screen.getByText(/words/)).toBeTruthy()
  })

  it('displays CSV content as monospace pre block', async () => {
    vi.mocked(documentsApi.getFile).mockResolvedValue(makeTextBlob('col1,col2\nval1,val2'))
    const { container } = render(<DocumentViewerModal filename="data.csv" onClose={() => {}} />)
    await waitFor(() => screen.getByText(/col1,col2/))
    expect(container.querySelector('pre')).toBeTruthy()
  })

  it('shows no content message when blob is empty', async () => {
    vi.mocked(documentsApi.getFile).mockResolvedValue(makeTextBlob(''))
    render(<DocumentViewerModal filename="empty.txt" onClose={() => {}} />)
    await waitFor(() => screen.getByText('No content found.'))
  })

  it('renders PDF as an iframe', async () => {
    const mockBlob = new Blob(['%PDF-1.4'], { type: 'application/pdf' })
    vi.mocked(documentsApi.getFile).mockResolvedValue(mockBlob)
    const createObjectURL = vi.fn(() => 'blob:fake-pdf-url')
    vi.stubGlobal('URL', { createObjectURL, revokeObjectURL: vi.fn() })
    const { container } = render(<DocumentViewerModal filename="report.pdf" onClose={() => {}} />)
    await waitFor(() => expect(container.querySelector('iframe')).toBeTruthy())
  })

  it('shows download link for Excel files', async () => {
    const mockBlob = new Blob([new Uint8Array([0x50, 0x4b, 0x03, 0x04])], {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })
    vi.mocked(documentsApi.getFile).mockResolvedValue(mockBlob)
    const createObjectURL = vi.fn(() => 'blob:fake-xlsx-url')
    vi.stubGlobal('URL', { createObjectURL, revokeObjectURL: vi.fn() })
    render(<DocumentViewerModal filename="data.xlsx" onClose={() => {}} />)
    await waitFor(() => screen.getByText(/Download data\.xlsx/))
  })

  it('calls getFile not getContent or getChunks', async () => {
    vi.mocked(documentsApi.getFile).mockResolvedValue(makeTextBlob('Some text.'))
    render(<DocumentViewerModal filename="doc.txt" onClose={() => {}} />)
    await waitFor(() => expect(documentsApi.getFile).toHaveBeenCalledWith('doc.txt'))
  })

  it('falls back to getContent when getFile returns 404 (legacy document)', async () => {
    const notFound = { response: { status: 404 } }
    vi.mocked(documentsApi.getFile).mockRejectedValue(notFound)
    vi.mocked(documentsApi.getContent).mockResolvedValue({
      filename: 'legacy.txt',
      content: 'Stitched chunk text for old doc.',
      word_count: 6,
    })
    render(<DocumentViewerModal filename="legacy.txt" onClose={() => {}} />)
    await waitFor(() => screen.getByText('Stitched chunk text for old doc.'))
    expect(documentsApi.getContent).toHaveBeenCalledWith('legacy.txt')
  })

  it('shows unavailable state and callback when file and content fallback are missing', async () => {
    const notFound = { response: { status: 404 } }
    const onUnavailable = vi.fn()
    vi.mocked(documentsApi.getFile).mockRejectedValue(notFound)
    vi.mocked(documentsApi.getContent).mockRejectedValue(notFound)
    render(<DocumentViewerModal filename="missing.txt" onClose={() => {}} onUnavailable={onUnavailable} />)
    await waitFor(() => screen.getByText('Document preview is no longer available.'))
    expect(onUnavailable).toHaveBeenCalledWith('missing.txt')
    expect(toast.error).not.toHaveBeenCalled()
  })

  it('shows an inline error when document file preview fails', async () => {
    vi.mocked(documentsApi.getFile).mockRejectedValue(new Error('preview failed'))
    render(<DocumentViewerModal filename="broken.txt" onClose={() => {}} />)
    await waitFor(() => screen.getByText('Error: preview failed'))
    expect(screen.queryByText('No content found.')).toBeNull()
  })

  it('hides Chunks tab for guest users', async () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    vi.mocked(useAuthStore).mockImplementation((selector: (s: any) => unknown) =>
      selector({ isGuest: true })
    )
    vi.mocked(documentsApi.getFile).mockResolvedValue(makeTextBlob('some text'))
    render(<DocumentViewerModal filename="doc.txt" onClose={() => {}} />)
    await waitFor(() => expect(documentsApi.getFile).toHaveBeenCalled())
    expect(screen.queryByTestId('tab-chunks')).toBeNull()
  })

  it('shows Content and Chunks tabs for admin users', async () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    vi.mocked(useAuthStore).mockImplementation((selector: (s: any) => unknown) =>
      selector({ isGuest: false })
    )
    vi.mocked(documentsApi.getFile).mockResolvedValue(makeTextBlob('some text'))
    render(<DocumentViewerModal filename="doc.txt" onClose={() => {}} />)
    await waitFor(() => expect(documentsApi.getFile).toHaveBeenCalled())
    expect(screen.getByTestId('tab-content')).toBeTruthy()
    expect(screen.getByTestId('tab-chunks')).toBeTruthy()
  })

  it('clicking Chunks tab loads and displays chunk cards', async () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    vi.mocked(useAuthStore).mockImplementation((selector: (s: any) => unknown) =>
      selector({ isGuest: false })
    )
    vi.mocked(documentsApi.getFile).mockResolvedValue(makeTextBlob('some text'))
    vi.mocked(documentsApi.getChunks).mockResolvedValue({
      filename: 'test.txt',
      chunks: ['chunk one', 'chunk two'],
      total_chunks: 2,
    })
    render(<DocumentViewerModal filename="test.txt" onClose={() => {}} />)
    await waitFor(() => expect(documentsApi.getFile).toHaveBeenCalled())
    await act(async () => { screen.getByTestId('tab-chunks').click() })
    await waitFor(() => screen.getByText('chunk one'))
    await act(async () => { await new Promise(r => setTimeout(r, 0)) })
    expect(screen.getByText('chunk two')).toBeTruthy()
  })

  it('shows an inline error when chunks fail to load', async () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    vi.mocked(useAuthStore).mockImplementation((selector: (s: any) => unknown) =>
      selector({ isGuest: false })
    )
    vi.mocked(documentsApi.getFile).mockResolvedValue(makeTextBlob('some text'))
    vi.mocked(documentsApi.getChunks).mockRejectedValue(new Error('chunks unavailable'))
    render(<DocumentViewerModal filename="test.txt" onClose={() => {}} />)
    await waitFor(() => expect(documentsApi.getFile).toHaveBeenCalled())
    await act(async () => { screen.getByTestId('tab-chunks').click() })
    await waitFor(() => screen.getByText('Error: chunks unavailable'))
    expect(screen.queryByText('No chunks found.')).toBeNull()
  })
})
