/**
 * Skill selection flow: SkillsPane → SkillTriggerContext → MessageInput chips.
 *
 * Uses the real SkillTriggerProvider so the sidebar and the chat input share
 * state exactly as in the app. Selecting a skill must create a chip (no trigger
 * text in the input), sending must pass the ids as selected_skill_ids and clear
 * the chips, and at most 3 skills can be selected.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, cleanup, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MessageInput } from '../MessageInput'
import { SkillsPane } from '../sidebar/SkillsPane'
import { SkillTriggerProvider } from '../../contexts/SkillTriggerContext'
import { skillsApi } from '../../lib/api'
import type { Skill } from '../../types'

vi.mock('../../contexts/MaterialAttachmentContext', () => ({
  useMaterialAttachment: () => ({ attachedMaterials: [], removeMaterial: vi.fn() }),
}))

vi.mock('../../contexts/TextQuoteContext', () => ({
  useTextQuote: () => ({ quotes: [], removeQuote: vi.fn() }),
}))

vi.mock('../../lib/api', () => ({
  skillsApi: {
    list: vi.fn(),
  },
}))

vi.mock('../VoiceInputButton', () => ({
  VoiceInputButton: () => null,
}))

vi.mock('../LazyMarkdown', () => ({
  LazyMarkdown: ({ children }: { children: string }) => <div>{children}</div>,
}))

// `t` must be referentially stable: MessageInput memoizes static suggestions on it.
const { mockT } = vi.hoisted(() => ({
  mockT: (key: string, options?: Record<string, unknown>) => {
    if (options?.returnObjects) return []
    if (key === 'chat:skill.removeSelected') return `remove ${String(options?.name)}`
    return key
  },
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: mockT,
    i18n: { language: 'zh' },
  }),
}))

const makeSkill = (id: string, name: string): Skill => ({
  id,
  name,
  description: null,
  triggers: [`/${id}`],
  instructions: `instructions of ${name}`,
  source: 'user',
  is_active: true,
})

const skills = [
  makeSkill('s1', '节奏控制'),
  makeSkill('s2', '人物塑造'),
  makeSkill('s3', '伏笔回收'),
  makeSkill('s4', '对白润色'),
]

function renderFlow(onSend = vi.fn()) {
  render(
    <SkillTriggerProvider>
      <SkillsPane />
      <MessageInput onSend={onSend} />
    </SkillTriggerProvider>,
  )
  return { onSend }
}

const selectButtonFor = (name: string) =>
  screen.getByRole('button', { name: `editor:fileTree.useSkill: ${name}` })

describe('Skill selection flow', () => {
  beforeEach(() => {
    vi.mocked(skillsApi.list).mockResolvedValue({ skills, total: skills.length })
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('selecting a skill in SkillsPane creates a chip and does not insert trigger text', async () => {
    const user = userEvent.setup({ delay: null })
    renderFlow()

    await screen.findByText('节奏控制')
    await user.click(selectButtonFor('节奏控制'))

    const row = screen.getByTestId('chat-selected-skill-row')
    expect(within(row).getByText('节奏控制')).toBeInTheDocument()
    expect(screen.getByTestId('chat-input')).toHaveValue('')
    // Already selected → the pane button reflects the state and cannot add a duplicate
    expect(selectButtonFor('节奏控制')).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getAllByTestId('chat-selected-skill-chip')).toHaveLength(1)
  })

  it('sends selected_skill_ids with the message and clears the chips', async () => {
    const user = userEvent.setup({ delay: null })
    const { onSend } = renderFlow()

    await screen.findByText('节奏控制')
    await user.click(selectButtonFor('节奏控制'))
    await user.click(selectButtonFor('伏笔回收'))

    await user.type(screen.getByTestId('chat-input'), '写下一章')
    await user.click(screen.getByTestId('send-button'))

    expect(onSend).toHaveBeenCalledWith('写下一章', ['s1', 's3'])
    expect(screen.queryByTestId('chat-selected-skill-row')).not.toBeInTheDocument()
  })

  it('removes a chip with its accessible remove button', async () => {
    const user = userEvent.setup({ delay: null })
    renderFlow()

    await screen.findByText('人物塑造')
    await user.click(selectButtonFor('人物塑造'))
    await user.click(screen.getByRole('button', { name: 'remove 人物塑造' }))

    expect(screen.queryByTestId('chat-selected-skill-row')).not.toBeInTheDocument()
  })

  it('allows at most 3 selected skills', async () => {
    const user = userEvent.setup({ delay: null })
    const { onSend } = renderFlow()

    await screen.findByText('对白润色')
    for (const name of ['节奏控制', '人物塑造', '伏笔回收']) {
      await user.click(selectButtonFor(name))
    }

    expect(screen.getAllByTestId('chat-selected-skill-chip')).toHaveLength(3)
    expect(selectButtonFor('对白润色')).toBeDisabled()

    await user.type(screen.getByTestId('chat-input'), '继续')
    await user.click(screen.getByTestId('send-button'))
    expect(onSend).toHaveBeenCalledWith('继续', ['s1', 's2', 's3'])
  })
})
