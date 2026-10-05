import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const workflow = readFileSync(
  new URL('../../.github/workflows/ci.yml', import.meta.url),
  'utf8',
);

const stepBody = (name, nextName) => {
  const start = workflow.indexOf(`- name: ${name}`);
  const end = workflow.indexOf(`- name: ${nextName}`, start + 1);
  assert.notEqual(start, -1, `missing CI step: ${name}`);
  assert.notEqual(end, -1, `missing following CI step: ${nextName}`);
  return workflow.slice(start, end);
};

test('backend coverage artifact comes from the gated unit suite, not the later flow suite', () => {
  const unit = stepBody('Run unit tests with pytest', 'Run flow tests');
  assert.match(unit, /pytest .*--cov=\..*--cov-report=xml/);
  assert.match(unit, /--cov-fail-under=80/);

  const flow = stepBody('Run flow tests', 'Register every production Prefect deployment');
  assert.match(flow, /pytest tests\/test_flows\b/);
  assert.match(flow, /--no-cov\b/);
});
