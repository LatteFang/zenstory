import { describe, expect, it } from 'vitest';
import { parseChatDisplayEvents } from '../chatDisplayEvents';
import type { ToolCall } from '../../types';

const timestamp = new Date('2026-10-05T10:00:00Z');
const tools: ToolCall[] = [
  { id: 'one', tool_name: 'query_files', arguments: {}, status: 'success', result: { items: [] } },
  { id: 'two', tool_name: 'edit_file', arguments: {}, status: 'error', error: 'Edit rejected' },
];
const t = (key: string, options?: Record<string, unknown>) => `${key}:${options?.agent ?? ''}`;

describe('persisted chat display sequence', () => {
  it('retains multiple tool cycles and controls, resolving the final tool state at its original position', () => {
    const events = [
      { type: 'content', content: 'First' },
      { type: 'tool_call', tool_call_index: 0 },
      { type: 'content', content: 'Second' },
      { type: 'handoff', data: { target_agent: 'writer', reason: 'Write' } },
      { type: 'agent_selected', data: { agent_type: 'writer', agent_name: 'Writer', iteration: 2, max_iterations: 4 } },
      { type: 'tool_call', tool_call_index: 1 },
      { type: 'content', content: 'Third' },
      { type: 'workflow_stopped', data: { reason: 'clarification_needed', question: 'Which ending?' } },
    ];
    const items = parseChatDisplayEvents(JSON.stringify({ display_events: events }), tools, timestamp, t)!;
    expect(items.map(item => item.type)).toEqual(['content', 'tool_calls', 'content', 'thinking_status', 'agent_selected', 'tool_calls', 'content', 'workflow_stopped']);
    expect(items[1].toolCalls).toEqual([tools[0]]);
    expect(items[5].toolCalls).toEqual([tools[1]]);
    expect(items[3].content).toBe('chat:workflow.handoffMessage:writer');
    expect(items[4].iteration).toBe(2);
    expect(items[7].question).toBe('Which ending?');
    expect(new Set(items.map(item => item.id)).size).toBe(events.length);
  });

  it.each([
    null, '{', '{}', '{"display_events":[]}',
    JSON.stringify({ display_events: [{ type: 'tool_call', tool_call_index: 9 }] }),
    JSON.stringify({ display_events: [{ type: 'tool_call', tool_call_index: -1 }] }),
    JSON.stringify({ display_events: [{ type: 'content', content: null }] }),
    JSON.stringify({ display_events: [{ type: 'future-event', data: {} }] }),
  ])('retains legacy rendering when original sequence is absent or invalid: %s', metadata => {
    expect(parseChatDisplayEvents(metadata, tools, timestamp, t)).toBeUndefined();
  });
});
