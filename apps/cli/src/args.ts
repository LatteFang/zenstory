import { parseArgs } from 'node:util';

import { CliError, EXIT } from './client.js';

export interface OptionSpec {
  type: 'string' | 'boolean';
  short?: string;
  multiple?: boolean;
  description: string;
  valueName?: string;
}

export type OptionValues = Record<string, string | boolean | string[] | undefined>;

export interface CommandDef<Ctx> {
  /** Space-separated command path, e.g. "files list". */
  name: string;
  summary: string;
  /** Positional arguments, e.g. ["<projectId>", "[query...]"]. */
  args?: string[];
  options?: Record<string, OptionSpec>;
  /** Extra help text (examples, endpoint). */
  details?: string;
  run: (ctx: Ctx, values: OptionValues, positionals: string[]) => Promise<void>;
}

export const GLOBAL_OPTIONS: Record<string, OptionSpec> = {
  json: { type: 'boolean', description: 'Machine-readable JSON output (recommended for agents)' },
  help: { type: 'boolean', short: 'h', description: 'Show help' },
  'allow-base-override': {
    type: 'boolean',
    description: 'Allow sending the saved key to a ZENSTORY_API_BASE other than the one it was saved for',
  },
};

const LEADING_FLAGS = new Set(['--json', '--help', '-h', '--allow-base-override']);

export type Route<Ctx> =
  | { kind: 'command'; command: CommandDef<Ctx>; rest: string[] }
  | { kind: 'group'; group: string; unknown?: string }
  | { kind: 'unknown'; token: string }
  | { kind: 'root' };

/** Match the longest command path at the start of argv. */
export function route<Ctx>(argv: string[], commands: CommandDef<Ctx>[]): Route<Ctx> {
  const words: string[] = [];
  for (const a of argv) {
    if (a.startsWith('-')) {
      // Only value-less global flags may precede the command words.
      if (LEADING_FLAGS.has(a)) continue;
      break;
    }
    words.push(a);
    if (words.length === 2) break;
  }
  if (words.length === 0) return { kind: 'root' };

  const byName = new Map(commands.map((c) => [c.name, c]));
  if (words.length === 2) {
    const two = byName.get(`${words[0]} ${words[1]}`);
    if (two) return { kind: 'command', command: two, rest: dropWords(argv, 2) };
  }
  const one = byName.get(words[0]);
  if (one) return { kind: 'command', command: one, rest: dropWords(argv, 1) };

  const isGroup = commands.some((c) => c.name.startsWith(`${words[0]} `));
  if (isGroup) return { kind: 'group', group: words[0], unknown: words[1] };
  return { kind: 'unknown', token: words[0] };
}

function dropWords(argv: string[], n: number): string[] {
  const out = [...argv];
  let removed = 0;
  for (let i = 0; i < out.length && removed < n; ) {
    if (!out[i].startsWith('-')) {
      out.splice(i, 1);
      removed++;
    } else {
      i++;
    }
  }
  return out;
}

export function parseCommandArgs<Ctx>(
  command: CommandDef<Ctx>,
  argv: string[],
): { values: OptionValues; positionals: string[] } {
  const options: Record<string, { type: 'string' | 'boolean'; short?: string; multiple?: boolean }> = {};
  for (const [name, spec] of Object.entries({ ...GLOBAL_OPTIONS, ...(command.options ?? {}) })) {
    // parseArgs rejects keys that are present but undefined.
    options[name] = { type: spec.type };
    if (spec.short) options[name].short = spec.short;
    if (spec.multiple) options[name].multiple = true;
  }
  try {
    const { values, positionals } = parseArgs({ args: argv, options, allowPositionals: true, strict: true });
    return { values: values as OptionValues, positionals };
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    throw new CliError(`${msg}\nRun \`zenstory ${command.name} --help\` for usage.`, EXIT.USAGE);
  }
}

/** Require N leading positionals, naming the missing one in the error. */
export function requirePositionals(command: { name: string; args?: string[] }, positionals: string[], n: number): void {
  if (positionals.length < n) {
    const missing = (command.args ?? [])[positionals.length] ?? 'argument';
    throw new CliError(
      `Missing ${missing}.\nUsage: zenstory ${command.name} ${(command.args ?? []).join(' ')}`.trimEnd(),
      EXIT.USAGE,
    );
  }
}

export function str(values: OptionValues, key: string): string | undefined {
  const v = values[key];
  return typeof v === 'string' ? v : undefined;
}

export function bool(values: OptionValues, key: string): boolean {
  return values[key] === true;
}

export function list(values: OptionValues, key: string): string[] {
  const v = values[key];
  if (Array.isArray(v)) return v.flatMap((x) => x.split(',')).map((x) => x.trim()).filter(Boolean);
  if (typeof v === 'string') return v.split(',').map((x) => x.trim()).filter(Boolean);
  return [];
}

export function int(values: OptionValues, key: string, min: number, max: number): number | undefined {
  const raw = str(values, key);
  if (raw === undefined) return undefined;
  const n = Number(raw);
  if (!Number.isInteger(n) || n < min || n > max) {
    throw new CliError(`--${key} must be an integer between ${min} and ${max} (got "${raw}").`, EXIT.USAGE);
  }
  return n;
}

function optionLabel(name: string, spec: OptionSpec): string {
  const short = spec.short ? `-${spec.short}, ` : '';
  const value = spec.type === 'string' ? ` <${spec.valueName ?? 'value'}>` : '';
  return `${short}--${name}${value}`;
}

export function formatOptions(options: Record<string, OptionSpec>): string {
  const entries = Object.entries(options).map(([name, spec]) => [optionLabel(name, spec), spec.description]);
  const width = Math.max(...entries.map(([l]) => l.length));
  return entries.map(([l, d]) => `  ${l.padEnd(width)}  ${d}`).join('\n');
}

export function commandHelp<Ctx>(command: CommandDef<Ctx>): string {
  const parts = [
    `Usage: zenstory ${command.name}${command.args?.length ? ` ${command.args.join(' ')}` : ''} [options]`,
    '',
    command.summary,
  ];
  if (command.details) parts.push('', command.details.trimEnd());
  parts.push('', 'Options:', formatOptions({ ...(command.options ?? {}), ...GLOBAL_OPTIONS }));
  return parts.join('\n');
}
