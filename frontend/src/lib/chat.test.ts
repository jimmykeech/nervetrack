import { describe, expect, it } from 'vitest';
import { applyEvent, initialStreamState, parseSseChunk } from './chat';

describe('applyEvent', () => {
  it('accumulates tokens', () => {
    let s = initialStreamState();
    s = applyEvent(s, { type: 'token', text: 'Hel' });
    s = applyEvent(s, { type: 'token', text: 'lo' });
    expect(s.streaming).toBe('Hello');
  });

  it('records active tool then clears on token', () => {
    let s = initialStreamState();
    s = applyEvent(s, { type: 'tool', name: 'list_weeks' });
    expect(s.tool).toBe('list_weeks');
    s = applyEvent(s, { type: 'token', text: 'x' });
    expect(s.tool).toBe(null);
  });

  it('final sets full content and done clears streaming', () => {
    let s = initialStreamState();
    s = applyEvent(s, { type: 'final', content: 'All done' });
    expect(s.streaming).toBe('All done');
    s = applyEvent(s, { type: 'done' });
    expect(s.done).toBe(true);
  });
});

describe('parseSseChunk', () => {
  it('parses complete frames and keeps the remainder', () => {
    const raw = 'data: {"type":"token","text":"a"}\n\ndata: {"type":"tool","nam';
    const { events, rest } = parseSseChunk(raw);
    expect(events).toEqual([{ type: 'token', text: 'a' }]);
    expect(rest).toBe('data: {"type":"tool","nam');
  });
});
