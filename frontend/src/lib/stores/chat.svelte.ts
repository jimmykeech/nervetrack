// Chat store: thread list + the active thread's messages, plus live SSE streaming
// of the assistant reply. Mirrors the timer store's Svelte-5 runes pattern.

import { api } from '$lib/api';
import { applyEvent, initialStreamState, parseSseChunk } from '$lib/chat';
import type { ChatMessage, ConversationSummary } from '$lib/types';

export class ChatStore {
  conversations = $state<ConversationSummary[]>([]);
  activeId = $state<string | null>(null);
  messages = $state<ChatMessage[]>([]);
  streaming = $state<string>('');
  tool = $state<string | null>(null);
  sending = $state<boolean>(false);
  error = $state<string>('');

  async loadList() {
    this.conversations = await api.listConversations();
  }

  async open(id: string) {
    this.activeId = id;
    const detail = await api.getConversation(id);
    this.messages = detail.messages;
    this.streaming = '';
    this.tool = null;
  }

  async newChat() {
    const conv = await api.createConversation();
    this.conversations = [conv, ...this.conversations];
    this.activeId = conv.id;
    this.messages = [];
    this.streaming = '';
    this.tool = null;
  }

  async remove(id: string) {
    await api.deleteConversation(id);
    this.conversations = this.conversations.filter((c) => c.id !== id);
    if (this.activeId === id) {
      this.activeId = null;
      this.messages = [];
    }
  }

  async send(content: string) {
    if (!this.activeId || this.sending) return;
    this.sending = true;
    this.error = '';
    const id = this.activeId;
    this.messages = [
      ...this.messages,
      { id: crypto.randomUUID(), role: 'user', content, created_at: new Date().toISOString() }
    ];

    let state = initialStreamState();
    try {
      const res = await fetch(`/api/v1/ai/conversations/${id}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ content })
      });
      if (!res.ok || !res.body) {
        this.error =
          res.status === 409 ? 'Configure a model in Settings first.' : `Error ${res.status}`;
        this.sending = false;
        return;
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const { events, rest } = parseSseChunk(buffer);
        buffer = rest;
        for (const ev of events) {
          state = applyEvent(state, ev);
          this.streaming = state.streaming;
          this.tool = state.tool;
        }
      }
    } catch (e) {
      this.error = (e as Error).message;
    }

    if (state.streaming) {
      this.messages = [
        ...this.messages,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: state.streaming,
          created_at: new Date().toISOString()
        }
      ];
    }
    this.streaming = '';
    this.tool = null;
    this.sending = false;
    // Refresh the list so a freshly-titled thread shows its title.
    await this.loadList();
  }
}
