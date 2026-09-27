import { describe, expect, it } from 'vitest';

import { int, list, parseCommandArgs, route, type CommandDef } from '../src/args.js';
import { CliError } from '../src/client.js';

const noop = async () => {};
const commands: CommandDef<unknown>[] = [
  { name: 'login', summary: '', options: { key: { type: 'string', description: '' } }, run: noop },
  { name: 'files list', summary: '', args: ['<projectId>'], options: { type: { type: 'string', description: '' } }, run: noop },
  { name: 'files get', summary: '', args: ['<fileId>'], run: noop },
  { name: 'search', summary: '', args: ['<projectId>', '<query...>'], options: { type: { type: 'string', multiple: true, description: '' } }, run: noop },
];

describe('route', () => {
  it('matches two-word commands and strips the command words', () => {
    const r = route(['files', 'list', 'p1', '--type', 'draft'], commands);
    expect(r.kind).toBe('command');
    if (r.kind === 'command') {
      expect(r.command.name).toBe('files list');
      expect(r.rest).toEqual(['p1', '--type', 'draft']);
    }
  });

  it('matches one-word commands whose positionals follow', () => {
    const r = route(['search', 'p1', 'dragon', 'lair'], commands);
    expect(r.kind === 'command' && r.command.name).toBe('search');
    if (r.kind === 'command') expect(r.rest).toEqual(['p1', 'dragon', 'lair']);
  });

  it('allows --json before the command', () => {
    const r = route(['--json', 'files', 'get', 'f1'], commands);
    expect(r.kind === 'command' && r.command.name).toBe('files get');
    if (r.kind === 'command') expect(r.rest).toEqual(['--json', 'f1']);
  });

  it('reports groups, unknown subcommands and unknown commands', () => {
    expect(route(['files'], commands)).toEqual({ kind: 'group', group: 'files', unknown: undefined });
    expect(route(['files', 'nope'], commands)).toEqual({ kind: 'group', group: 'files', unknown: 'nope' });
    expect(route(['bogus'], commands)).toEqual({ kind: 'unknown', token: 'bogus' });
    expect(route([], commands)).toEqual({ kind: 'root' });
  });
});

describe('parseCommandArgs', () => {
  it('parses options, globals and positionals', () => {
    const { values, positionals } = parseCommandArgs(commands[1], ['p1', '--type', 'draft', '--json']);
    expect(values.type).toBe('draft');
    expect(values.json).toBe(true);
    expect(positionals).toEqual(['p1']);
  });

  it('accepts "-" as an option value (stdin)', () => {
    const { values } = parseCommandArgs(commands[0], ['--key', '-']);
    expect(values.key).toBe('-');
  });

  it('collects repeatable options', () => {
    const { values } = parseCommandArgs(commands[3], ['p1', 'q', '--type', 'lore', '--type', 'character']);
    expect(list(values, 'type')).toEqual(['lore', 'character']);
  });

  it('rejects unknown options as usage errors', () => {
    try {
      parseCommandArgs(commands[1], ['p1', '--nope']);
      expect.unreachable();
    } catch (err) {
      expect(err).toBeInstanceOf(CliError);
      expect((err as CliError).exitCode).toBe(2);
      expect((err as CliError).message).toContain('zenstory files list --help');
    }
  });
});

describe('value helpers', () => {
  it('validates integer ranges', () => {
    expect(int({ limit: '5' }, 'limit', 1, 50)).toBe(5);
    expect(int({}, 'limit', 1, 50)).toBeUndefined();
    expect(() => int({ limit: '0' }, 'limit', 1, 50)).toThrow(/between 1 and 50/);
    expect(() => int({ limit: 'abc' }, 'limit', 1, 50)).toThrow(CliError);
  });

  it('splits comma-separated lists', () => {
    expect(list({ type: 'lore, character' }, 'type')).toEqual(['lore', 'character']);
    expect(list({ type: ['a,b', 'c'] }, 'type')).toEqual(['a', 'b', 'c']);
  });
});
