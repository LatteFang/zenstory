import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

describe('reduced-motion stylesheet contract', () => {
  it('disables ambient, loading, and entrance motion without hiding progress UI', () => {
    const css = readFileSync('src/index.css', 'utf8');
    const reducedMotion = css.match(/@media \(prefers-reduced-motion: reduce\) \{[\s\S]*?\n\}/)?.[0] ?? '';

    expect(reducedMotion).toContain('.animate-float');
    expect(reducedMotion).toContain('.skeleton-shimmer');
    expect(reducedMotion).toContain('.animate-pulse');
    expect(reducedMotion).toContain('.animate-scale-in');
    expect(reducedMotion).toContain('animation: none !important');
    expect(reducedMotion).not.toContain('display: none');
  });
});
