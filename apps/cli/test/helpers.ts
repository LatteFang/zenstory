import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { run, type Io } from '../src/app.js';

export interface Call {
  url: string;
  method: string;
  headers: Record<string, string>;
  body: unknown;
}

export type Responder = (call: Call) => { status?: number; body?: unknown; headers?: Record<string, string> };

export function tempDir(prefix = 'zenstory-test-'): string {
  return mkdtempSync(join(tmpdir(), prefix));
}

export function mockFetch(responder: Responder) {
  const calls: Call[] = [];
  const fetch = async (input: string, init?: RequestInit): Promise<Response> => {
    const call: Call = {
      url: input,
      method: init?.method ?? 'GET',
      headers: (init?.headers ?? {}) as Record<string, string>,
      body: typeof init?.body === 'string' ? JSON.parse(init.body) : undefined,
    };
    calls.push(call);
    const r = responder(call);
    const text = r.body === undefined ? '' : typeof r.body === 'string' ? r.body : JSON.stringify(r.body);
    return new Response(text, { status: r.status ?? 200, headers: r.headers });
  };
  return { fetch, calls };
}

export async function runCli(
  argv: string[],
  opts: {
    env?: Record<string, string | undefined>;
    fetch?: Io['fetch'];
    stdin?: string;
    home?: string;
    cwd?: string;
    promptSecret?: Io['promptSecret'];
  } = {},
) {
  let stdout = '';
  let stderr = '';
  const code = await run(argv, {
    stdout: { write: (s: string) => (stdout += s) },
    stderr: { write: (s: string) => (stderr += s) },
    env: opts.env ?? {},
    fetch: opts.fetch,
    readStdin: async () => opts.stdin ?? '',
    promptSecret: opts.promptSecret,
    home: opts.home,
    cwd: opts.cwd,
  });
  return { code, stdout, stderr };
}

export const KEY = `eg_${'a1b2'.repeat(16)}`;
