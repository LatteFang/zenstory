import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { FileSearchProvider } from '../../../contexts/FileSearchContext';
import { FileTreePane } from '../FileTreePane';

const mocks = vi.hoisted(() => ({
  select: vi.fn(),
  switchToEditor: vi.fn(),
  clearSearch: vi.fn(),
  getTree: vi.fn(),
  results: [{ id: 'draft-1', fileType: 'draft', title: 'Draft' }],
}));

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('../../../contexts/ProjectContext', () => ({
  useProject: () => ({ currentProjectId: 'project-1', selectedItem: null, setSelectedItem: mocks.select, fileTreeVersion: 0 }),
}));
vi.mock('../../../contexts/MobileLayoutContext', () => ({
  useMobileLayout: () => ({ isMobile: false, switchToEditor: mocks.switchToEditor }),
}));
vi.mock('../../../contexts/MaterialAttachmentContext', () => ({
  MAX_ATTACHED_MATERIALS: 5,
  useMaterialAttachment: () => ({ addMaterial: vi.fn(), removeMaterial: vi.fn(), isMaterialAttached: () => false, isAtLimit: false }),
}));
vi.mock('../../../lib/api', () => ({ fileApi: { getTree: mocks.getTree } }));
vi.mock('../../../hooks/useFileSearch', () => ({
  useFileSearch: () => ({ results: mocks.results, isSearching: false, clearSearch: mocks.clearSearch }),
}));
vi.mock('../../SearchResultsDropdown', () => ({
  default: ({ onClose }: { onClose: () => void }) => <div data-testid="search-results"><button onClick={onClose}>Close results</button></div>,
}));

async function openSearch() {
  render(<FileSearchProvider><FileTreePane /></FileSearchProvider>);
  const input = await screen.findByRole('searchbox');
  fireEvent.change(input, { target: { value: 'Draft' } });
  expect(screen.getByTestId('search-results')).toBeInTheDocument();
  return input;
}

describe('FileTreePane search navigation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getTree.mockResolvedValue({ tree: [{ id: 'draft-1', title: 'Draft', file_type: 'draft', children: [] }] });
  });

  it('does not focus/open search merely because a project is loaded', async () => {
    render(<FileSearchProvider><FileTreePane /></FileSearchProvider>);
    expect(await screen.findByRole('searchbox')).not.toHaveFocus();
  });

  it.each([{ isComposing: true }, { keyCode: 229 }])('ignores native composition navigation %o without cancelling IME', async (flags) => {
    await openSearch();
    const event = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true, ...flags });
    fireEvent(window, event);
    expect(event.defaultPrevented).toBe(false);
    expect(mocks.select).not.toHaveBeenCalled();
    expect(screen.getByTestId('search-results')).toBeInTheDocument();
  });

  it('only selects after composition ends and closes results', async () => {
    const input = await openSearch();
    fireEvent.compositionStart(input);
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(mocks.select).not.toHaveBeenCalled();
    fireEvent.compositionEnd(input);
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(mocks.select).toHaveBeenCalledTimes(1);
    expect(mocks.select).toHaveBeenCalledWith({ id: 'draft-1', type: 'draft', title: 'Draft' });
    expect(screen.queryByTestId('search-results')).not.toBeInTheDocument();
  });

  it.each(['escape', 'clear', 'close'])('closes results via %s', async (action) => {
    const input = await openSearch();
    if (action === 'escape') fireEvent.keyDown(input, { key: 'Escape' });
    if (action === 'clear') fireEvent.click(screen.getByRole('button', { name: 'Clear search' }));
    if (action === 'close') fireEvent.click(screen.getByRole('button', { name: 'Close results' }));
    expect(screen.queryByTestId('search-results')).not.toBeInTheDocument();
  });
});
