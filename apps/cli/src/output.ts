/** Terminal width of a string: CJK / full-width characters count as 2 columns. */
export function displayWidth(s: string): number {
  let w = 0;
  for (const ch of s) {
    const cp = ch.codePointAt(0) ?? 0;
    if (cp < 0x20 || (cp >= 0x7f && cp < 0xa0)) continue;
    w += isWide(cp) ? 2 : 1;
  }
  return w;
}

function isWide(cp: number): boolean {
  return (
    (cp >= 0x1100 && cp <= 0x115f) ||
    (cp >= 0x2e80 && cp <= 0x303e) ||
    (cp >= 0x3041 && cp <= 0x33ff) ||
    (cp >= 0x3400 && cp <= 0x4dbf) ||
    (cp >= 0x4e00 && cp <= 0x9fff) ||
    (cp >= 0xa000 && cp <= 0xa4cf) ||
    (cp >= 0xac00 && cp <= 0xd7a3) ||
    (cp >= 0xf900 && cp <= 0xfaff) ||
    (cp >= 0xfe30 && cp <= 0xfe4f) ||
    (cp >= 0xff00 && cp <= 0xff60) ||
    (cp >= 0xffe0 && cp <= 0xffe6) ||
    (cp >= 0x1f300 && cp <= 0x1faff) ||
    (cp >= 0x20000 && cp <= 0x3fffd)
  );
}

export function truncate(s: string, max: number): string {
  if (displayWidth(s) <= max) return s;
  let out = '';
  let w = 0;
  for (const ch of s) {
    const cw = isWide(ch.codePointAt(0) ?? 0) ? 2 : 1;
    if (w + cw > max - 1) break;
    out += ch;
    w += cw;
  }
  return `${out}…`;
}

function pad(s: string, width: number): string {
  return s + ' '.repeat(Math.max(0, width - displayWidth(s)));
}

export interface Column<T> {
  header: string;
  get: (row: T) => unknown;
  max?: number;
}

export function formatTable<T>(rows: T[], columns: Column<T>[]): string {
  const cells = rows.map((row) =>
    columns.map((c) => {
      const v = c.get(row);
      const s = v == null ? '' : String(v).replace(/\s+/g, ' ');
      return c.max ? truncate(s, c.max) : s;
    }),
  );
  const widths = columns.map((c, i) => Math.max(displayWidth(c.header), ...cells.map((r) => displayWidth(r[i]))));
  const line = (vals: string[]) =>
    vals
      .map((v, i) => (i === vals.length - 1 ? v : pad(v, widths[i])))
      .join('  ')
      .trimEnd();
  return [line(columns.map((c) => c.header)), ...cells.map(line)].join('\n');
}

export function formatKeyValues(pairs: Array<[string, unknown]>): string {
  const width = Math.max(...pairs.map(([k]) => k.length));
  return pairs.map(([k, v]) => `${k.padEnd(width)}  ${v == null || v === '' ? '-' : String(v)}`).join('\n');
}

export function toJson(data: unknown): string {
  return JSON.stringify(data, null, 2);
}
