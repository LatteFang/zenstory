import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useDashboardInspirations } from "../../hooks/useDashboardInspirations";
import type { ProjectType } from "../../types";

interface DashboardInspirationSuggestionsProps {
  projectType: ProjectType;
  onSelect: (inspiration: string) => void;
}

export function DashboardInspirationSuggestions({
  projectType,
  onSelect,
}: DashboardInspirationSuggestionsProps) {
  const { t } = useTranslation("dashboard");
  const [refreshSeed, setRefreshSeed] = useState(0);
  const inspirations = useDashboardInspirations(projectType, 2, refreshSeed);

  if (inspirations.length === 0) {
    return null;
  }

  return (
    <div className="mt-5 flex flex-col gap-3" data-testid="dashboard-real-inspirations">
      <div className="text-[12px] tracking-[0.02em] text-[hsl(var(--text-secondary)/0.62)]">
        {t("dashboard.realInspirationsTitle", {
          defaultValue: "如果你还没想好，可以从这里开始：",
        })}
      </div>
      <div className="flex flex-col gap-3">
        {inspirations.map((item, index) => (
          <button
            key={item.id}
            type="button"
            title={`${item.title}｜${item.hook}`}
            aria-label={item.title}
            onClick={() => onSelect(`《${item.title}》：${item.hook}`)}
            className="grid grid-cols-[18px_minmax(0,1fr)] items-start gap-3 text-left transition-colors duration-150 hover:text-[hsl(var(--text-primary))]"
          >
            <span className="pt-0.5 text-[13px] leading-7 text-[hsl(var(--text-secondary)/0.36)]">
              {index + 1}
            </span>
            <span className="max-w-[760px] text-[14px] leading-7 text-[hsl(var(--text-secondary)/0.84)]">
              {item.hook}
            </span>
          </button>
        ))}
      </div>
      <button
        type="button"
        onClick={() => setRefreshSeed((current) => current + 1)}
        className="w-fit text-[12px] text-[hsl(var(--text-secondary)/0.58)] transition-colors hover:text-[hsl(var(--text-primary))]"
      >
        {t("dashboard.realInspirationsRefresh", { defaultValue: "换一批" })}
      </button>
    </div>
  );
}
