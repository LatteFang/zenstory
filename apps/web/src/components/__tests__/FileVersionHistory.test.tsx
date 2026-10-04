import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
const { getVersions, rollback, t } = vi.hoisted(() => ({
  getVersions: vi.fn(), rollback: vi.fn(), t: (key: string) => key,
}))
vi.mock('../../lib/api', () => ({ fileVersionApi: { getVersions, rollback } }))
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t }) }))
vi.mock('../subscription/UpgradePromptModal', () => ({ UpgradePromptModal: () => null }))
import { FileVersionHistory } from '../FileVersionHistory'

describe('FileVersionHistory saved-state boundary', () => {
  it('allows restoring the latest saved version when unversioned edits may have advanced', async () => {
    getVersions.mockResolvedValue({ total:1, versions:[{id:'version-1',version_number:3,change_type:'edit',change_source:'user',created_at:'2026-10-04T00:00:00Z',word_count:10,lines_added:1,lines_removed:0}] })
    rollback.mockResolvedValue({})
    vi.stubGlobal('confirm',vi.fn(()=>true))
    const onRollback=vi.fn()
    render(<FileVersionHistory fileId="file-1" fileTitle="Draft" onClose={vi.fn()} onRollback={onRollback} />)
    expect(await screen.findByText('latestSaved')).toBeInTheDocument()
    fireEvent.click(screen.getByTitle('rollback'))
    await waitFor(()=>expect(rollback).toHaveBeenCalledWith('file-1',3))
    await waitFor(()=>expect(onRollback).toHaveBeenCalledWith(3))
    vi.unstubAllGlobals()
  })
})
