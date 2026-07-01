// Pure helpers for the chat SSE stream: framing + a reducer over stream events.
// Kept UI-free so it is unit-testable.

export type ChatEvent =
  | { type: 'token'; text: string }
  | { type: 'tool'; name: string }
  | { type: 'final'; content: string }
  | { type: 'done' };

export interface StreamState {
  streaming: string;
  tool: string | null;
  done: boolean;
}

export function initialStreamState(): StreamState {
  return { streaming: '', tool: null, done: false };
}

export function applyEvent(state: StreamState, event: ChatEvent): StreamState {
  switch (event.type) {
    case 'token':
      return { ...state, streaming: state.streaming + event.text, tool: null };
    case 'tool':
      return { ...state, tool: event.name };
    case 'final':
      return { ...state, streaming: event.content, tool: null };
    case 'done':
      return { ...state, done: true };
  }
}

// Split an accumulating SSE buffer into complete `data: {...}\n\n` frames.
// Returns parsed events plus the trailing partial frame to carry forward.
export function parseSseChunk(buffer: string): { events: ChatEvent[]; rest: string } {
  const events: ChatEvent[] = [];
  const parts = buffer.split('\n\n');
  const rest = parts.pop() ?? '';
  for (const part of parts) {
    const line = part.trim();
    if (!line.startsWith('data:')) continue;
    try {
      events.push(JSON.parse(line.slice(5).trim()) as ChatEvent);
    } catch {
      /* ignore malformed frame */
    }
  }
  return { events, rest };
}
