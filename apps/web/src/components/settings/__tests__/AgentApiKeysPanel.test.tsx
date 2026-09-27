import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactElement } from 'react'

const { listMock, createMock, apiBaseMock } = vi.hoisted(() => ({
  listMock: vi.fn(),
  createMock: vi.fn(),
  apiBaseMock: vi.fn(() => 'https://api.zenstory.ai'),
}))

vi.mock('../../../lib/apiClient', () => ({
  getApiBase: apiBaseMock,
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string) => (typeof fallback === 'string' ? fallback : key),
    i18n: { language: 'zh' },
  }),
}))

vi.mock('../../../lib/api', () => ({
  agentApiKeysApi: {
    list: listMock,
    create: createMock,
    update: vi.fn(),
    delete: vi.fn(),
    regenerate: vi.fn(),
  },
}))

import { AgentApiKeysPanel } from '../AgentApiKeysPanel'

const renderPanel = (ui: ReactElement) => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const makeKey = () => ({
  id: 'key-1',
  name: 'My key',
  key_prefix: 'eg_abcd',
  scopes: ['read'],
  is_active: true,
  request_count: 0,
  created_at: '2026-09-01T00:00:00Z',
  updated_at: '2026-09-01T00:00:00Z',
})

describe('AgentApiKeysPanel', () => {
  beforeEach(() => {
    listMock.mockReset()
    createMock.mockReset()
    apiBaseMock.mockReset()
    apiBaseMock.mockReturnValue('https://api.zenstory.ai')
  })

  it('shows the CLI connect guide when the user has no keys', async () => {
    listMock.mockResolvedValue({ keys: [] })
    renderPanel(<AgentApiKeysPanel />)

    expect(await screen.findByText('apiKeys.connectGuide.title')).toBeInTheDocument()
    expect(screen.getByText('npx zenstory login')).toBeInTheDocument()
    expect(screen.getByText('apiKeys.connectGuide.step2Hint')).toBeInTheDocument()
    expect(screen.getByText('npx zenstory skill install')).toBeInTheDocument()
    expect(screen.getByText('apiKeys.noKeys')).toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/--key|<[^>]*key[^>]*>/i)
    expect(screen.getByRole('link', { name: 'https://api.zenstory.ai/skill.md' })).toHaveAttribute(
      'href',
      'https://api.zenstory.ai/skill.md',
    )
  })

  it('points self-hosted deployments at their own API base', async () => {
    apiBaseMock.mockReturnValue('https://zenstory.example.com/')
    listMock.mockResolvedValue({ keys: [] })
    renderPanel(<AgentApiKeysPanel />)

    expect(
      await screen.findByText('npx zenstory login --api-base https://zenstory.example.com/api/v1'),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'https://zenstory.example.com/skill.md' })).toHaveAttribute(
      'href',
      'https://zenstory.example.com/skill.md',
    )
  })

  it('announces copies to screen readers and hides decorative step numbers', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    listMock.mockResolvedValue({ keys: [makeKey()] })
    renderPanel(<AgentApiKeysPanel />)

    expect(await screen.findByRole('button', { name: 'apiKeys.copyPrefix' })).toBeInTheDocument()
    const guide = screen.getByRole('region', { name: 'apiKeys.connectGuide.title' })
    guide.querySelectorAll('ol > li > span:first-child').forEach((span) => {
      expect(span).toHaveAttribute('aria-hidden', 'true')
    })

    fireEvent.click(screen.getAllByRole('button', { name: 'apiKeys.copy' })[0])
    await waitFor(() => {
      expect(screen.getAllByRole('status').some((el) => el.textContent === 'apiKeys.copied')).toBe(true)
    })
    expect(writeText).toHaveBeenCalledWith('npx zenstory login')
  })

  it('keeps the connect guide above the key list', async () => {
    listMock.mockResolvedValue({ keys: [makeKey()] })
    renderPanel(<AgentApiKeysPanel />)

    expect(await screen.findByText('My key')).toBeInTheDocument()
    expect(screen.getByText('apiKeys.connectGuide.title')).toBeInTheDocument()
  })

  it('gives terminal commands instead of a chat prompt after creating a key', async () => {
    listMock.mockResolvedValueOnce({ keys: [] }).mockResolvedValue({ keys: [makeKey()] })
    createMock.mockResolvedValue({ key: 'eg_secret123', api_key: makeKey() })
    renderPanel(<AgentApiKeysPanel />)

    fireEvent.click(await screen.findByText('apiKeys.create'))
    fireEvent.change(screen.getByPlaceholderText('apiKeys.form.namePlaceholder'), {
      target: { value: 'CLI' },
    })
    fireEvent.submit(screen.getByPlaceholderText('apiKeys.form.namePlaceholder').closest('form')!)

    const dialog = await screen.findByRole('dialog', { name: 'apiKeys.createdTitle' })
    await waitFor(() => {
      expect(dialog).toHaveTextContent('npx zenstory login')
    })
    // The key is shown once (with its own copy button) but never embedded in a shell command.
    expect(dialog).toHaveTextContent('eg_secret123')
    expect(dialog).not.toHaveTextContent('--key')
    expect(dialog).toHaveTextContent('apiKeys.connectGuide.step2Hint')
    expect(dialog).toHaveTextContent('npx zenstory skill install')
    expect(dialog).not.toHaveTextContent('X-Agent-API-Key')
    expect(screen.getByRole('button', { name: 'apiKeys.copyKey' })).toBeInTheDocument()
  })
})
