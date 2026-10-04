import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, within } from "@testing-library/react";

import FeedbackManagement from "../FeedbackManagement";

const useQueryMock = vi.fn();
const useMutationMock = vi.fn();
const invalidateQueriesMock = vi.fn();
const mutateMock = vi.fn();
const getScreenshotBlobMock = vi.fn();

vi.mock("../../../lib/adminApi", () => ({
  adminApi: {
    getFeedbackList: vi.fn(),
    updateFeedbackStatus: vi.fn(),
    getFeedbackScreenshotBlob: (...args: unknown[]) => getScreenshotBlobMock(...args),
  },
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock("@tanstack/react-query", () => ({
  useQuery: (...args: unknown[]) => useQueryMock(...args),
  useMutation: (...args: unknown[]) => useMutationMock(...args),
  useQueryClient: () => ({
    invalidateQueries: invalidateQueriesMock,
  }),
}));

vi.mock("../../../hooks/useMediaQuery", () => ({
  useIsMobile: () => false,
}));

describe("FeedbackManagement", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useMutationMock.mockReturnValue({
      mutate: mutateMock,
      isPending: false,
    });
  });

  it("shows loading state", () => {
    useQueryMock.mockReturnValue({
      data: undefined,
      isLoading: true,
      isFetching: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<FeedbackManagement />);
    expect(screen.getByText("common:loading")).toBeInTheDocument();
  });

  it("shows error state and supports retry", () => {
    const refetchMock = vi.fn();
    useQueryMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      isFetching: false,
      isError: true,
      error: new Error("load feedback failed"),
      refetch: refetchMock,
    });

    render(<FeedbackManagement />);
    expect(screen.getByText("load feedback failed")).toBeInTheDocument();

    fireEvent.click(screen.getByText("common:retry"));
    expect(refetchMock).toHaveBeenCalledTimes(1);
  });

  it("shows empty state", () => {
    useQueryMock.mockReturnValue({
      data: { items: [], total: 0 },
      isLoading: false,
      isFetching: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<FeedbackManagement />);
    expect(screen.getByText("feedback.empty")).toBeInTheDocument();
  });

  it("renders table rows and updates feedback status", () => {
    useQueryMock.mockReturnValue({
      data: {
        items: [
          {
            id: "fb-1",
            user_id: "user-1",
            username: "feedback_user",
            email: "feedback_user@example.com",
            source_page: "editor",
            source_route: "/project/test",
            issue_text: "Toolbar overlaps on mobile",
            has_screenshot: true,
            screenshot_original_name: "bug.png",
            screenshot_content_type: "image/png",
            screenshot_size_bytes: 1024,
            screenshot_download_url: "/api/admin/feedback/fb-1/screenshot",
            status: "open",
            created_at: "2026-03-08T00:00:00Z",
            updated_at: "2026-03-08T00:00:00Z",
          },
        ],
        total: 1,
      },
      isLoading: false,
      isFetching: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<FeedbackManagement />);

    const issueText = screen.getByText("Toolbar overlaps on mobile");
    expect(issueText).toBeInTheDocument();
    expect(screen.getByText("feedback.viewScreenshot")).toBeInTheDocument();

    const row = issueText.closest("tr");
    expect(row).not.toBeNull();
    const statusSelect = within(row as HTMLTableRowElement).getByRole("combobox");
    fireEvent.change(statusSelect, { target: { value: "resolved" } });

    expect(mutateMock).toHaveBeenCalledWith({ id: "fb-1", status: "resolved" });
  });

  it("does not create or commit a screenshot URL after the preview closes", async () => {
    let resolveBlob!: (value: Blob) => void;
    getScreenshotBlobMock.mockReturnValueOnce(new Promise((resolve) => { resolveBlob = resolve; }));
    const createObjectURL = vi.fn(() => "blob:late");
    const revokeObjectURL = vi.fn();
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createObjectURL });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revokeObjectURL });
    useQueryMock.mockReturnValue({
      data: { items: [{
        id: "fb-late", user_id: "user-1", username: "late_user", email: "late@example.com",
        source_page: "editor", source_route: "/project/test", issue_text: "Late screenshot",
        has_screenshot: true, screenshot_original_name: "late.png", screenshot_content_type: "image/png",
        screenshot_size_bytes: 10, status: "open", created_at: "2026-03-08T00:00:00Z",
        updated_at: "2026-03-08T00:00:00Z",
      }], total: 1 },
      isLoading: false, isFetching: false, isError: false, error: null, refetch: vi.fn(),
    });
    render(<FeedbackManagement />);
    fireEvent.click(screen.getByText("feedback.viewScreenshot"));
    fireEvent.click(screen.getByText("common:close"));
    await act(async () => { resolveBlob(new Blob(["image"])); await Promise.resolve(); });
    expect(createObjectURL).not.toHaveBeenCalled();
    expect(screen.queryByAltText("feedback.screenshotPreviewAlt")).not.toBeInTheDocument();
  });
});
