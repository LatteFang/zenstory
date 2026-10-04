import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import SkillReviewPage from "../SkillReviewPage";
import { adminApi } from "../../../lib/adminApi";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock("../../../lib/adminApi", () => ({
  adminApi: {
    getPendingSkills: vi.fn(),
    approveSkill: vi.fn(),
    rejectSkill: vi.fn(),
  },
}));

describe("SkillReviewPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows loading state while pending skills are being loaded", () => {
    (adminApi.getPendingSkills as Mock).mockReturnValue(new Promise(() => {}));

    render(<SkillReviewPage />);
    expect(screen.getByText("common:loading")).toBeInTheDocument();
  });

  it("shows empty state when no pending skills exist", async () => {
    (adminApi.getPendingSkills as Mock).mockResolvedValue([]);

    render(<SkillReviewPage />);

    await waitFor(() => {
      expect(screen.getByText("admin:skills.noPending")).toBeInTheDocument();
    });
  });

  it("shows blocking error when initial load fails", async () => {
    (adminApi.getPendingSkills as Mock).mockRejectedValue(new Error("load pending skills failed"));

    render(<SkillReviewPage />);

    await waitFor(() => {
      expect(screen.getByText("load pending skills failed")).toBeInTheDocument();
    });
  });

  it("shows review history metadata for the selected status", async () => {
    (adminApi.getPendingSkills as Mock).mockResolvedValue([{
      id: "skill-1",
      name: "Reviewed skill",
      description: null,
      instructions: "Do it",
      category: "writing",
      author_id: "author-1",
      author_name: "Author",
      status: "rejected",
      reviewed_by: "admin-1",
      reviewer_name: "Reviewer",
      reviewed_at: "2026-10-04T00:00:00Z",
      rejection_reason: "Needs work",
      created_at: "2026-10-03T00:00:00Z",
    }]);

    render(<SkillReviewPage />);
    fireEvent.change(screen.getByLabelText("admin:skills.statusFilter"), {
      target: { value: "rejected" },
    });

    await waitFor(() => expect(adminApi.getPendingSkills).toHaveBeenLastCalledWith("rejected"));
    expect(screen.getByText(/Reviewer/)).toBeInTheDocument();
    expect(screen.getByText(/Needs work/)).toBeInTheDocument();
  });

  it("requires explicit approval confirmation and shows decision failures", async () => {
    (adminApi.getPendingSkills as Mock).mockResolvedValue([{
      id: "skill-2",
      name: "Pending skill",
      description: null,
      instructions: "Do it",
      category: "writing",
      author_id: null,
      author_name: null,
      status: "pending",
      reviewed_by: null,
      reviewer_name: null,
      reviewed_at: null,
      rejection_reason: null,
      created_at: "2026-10-03T00:00:00Z",
    }]);
    (adminApi.approveSkill as Mock).mockRejectedValue(new Error("approval conflict"));

    render(<SkillReviewPage />);
    await screen.findByText("Pending skill");
    fireEvent.click(screen.getByRole("button", { name: "admin:skills.approve" }));
    expect(adminApi.approveSkill).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "admin:skills.confirmApprove" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("approval conflict");
  });
});
