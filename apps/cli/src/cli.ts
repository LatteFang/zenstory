#!/usr/bin/env node
import { run } from './app.js';
import { CliError } from './client.js';

async function readStdin(): Promise<string> {
  const chunks: Buffer[] = [];
  for await (const chunk of process.stdin) chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
  return Buffer.concat(chunks).toString('utf8');
}

/** Read a line from the terminal in raw mode so the secret is never echoed. */
function promptSecret(prompt: string): Promise<string> {
  const stdin = process.stdin;
  return new Promise((resolve, reject) => {
    let raw = '';
    const finish = (err?: Error) => {
      stdin.off('data', onData);
      stdin.setRawMode(false);
      stdin.pause();
      process.stderr.write('\n');
      if (err) return reject(err);
      // Drop bracketed-paste markers and any other control characters.
      resolve(raw.replace(/\x1b\[20[01]~/g, '').replace(/[\x00-\x1f\x7f]/g, ''));
    };
    const onData = (chunk: Buffer | string) => {
      for (const ch of chunk.toString()) {
        if (ch === '\r' || ch === '\n' || ch === '\u0004') return finish();
        if (ch === '\u0003') return finish(new CliError('Aborted.', 130));
        if (ch === '\u007f' || ch === '\b') raw = raw.slice(0, -1);
        else raw += ch;
      }
    };
    process.stderr.write(prompt);
    stdin.setRawMode(true);
    stdin.resume();
    stdin.on('data', onData);
  });
}

const code = await run(process.argv.slice(2), {
  stdout: process.stdout,
  stderr: process.stderr,
  env: process.env,
  readStdin,
  promptSecret: process.stdin.isTTY ? promptSecret : undefined,
});
process.exitCode = code;
