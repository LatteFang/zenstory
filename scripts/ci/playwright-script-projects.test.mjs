import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const web = new URL('../../apps/web/', import.meta.url);

test('web E2E scripts select only configured Playwright projects', () => {
  const scripts = JSON.parse(readFileSync(new URL('package.json', web), 'utf8')).scripts;
  const config = readFileSync(new URL('playwright.config.ts', web), 'utf8');
  const projects = new Set([...config.matchAll(/name:\s*['"]([^'"]+)['"]/g)].map((match) => match[1]));
  for (const [name, command] of Object.entries(scripts)) {
    if (!command.startsWith('playwright test') || command.includes('--config=')) continue;
    for (const [, project] of command.matchAll(/--project=([\w-]+)/g)) {
      assert.ok(projects.has(project), `${name} selects unconfigured project ${project}`);
    }
  }
});
