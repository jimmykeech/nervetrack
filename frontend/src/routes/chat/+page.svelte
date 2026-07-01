<script lang="ts">
  import { onMount } from 'svelte';
  import { ChatStore } from '$lib/stores/chat.svelte';

  const chat = new ChatStore();
  let draft = $state('');

  onMount(async () => {
    await chat.loadList();
    if (chat.conversations.length) await chat.open(chat.conversations[0].id);
  });

  async function submit(e: Event) {
    e.preventDefault();
    const text = draft.trim();
    if (!text) return;
    if (!chat.activeId) await chat.newChat();
    draft = '';
    await chat.send(text);
  }
</script>

<div class="chat-layout">
  <aside class="card threads">
    <button class="newchat" onclick={() => chat.newChat()}>+ New chat</button>
    {#each chat.conversations as c}
      <div class="thread {chat.activeId === c.id ? 'sel' : ''}">
        <button class="threadname" onclick={() => chat.open(c.id)}>
          {c.title ?? 'New chat'}
        </button>
        <button class="del" title="Delete" onclick={() => chat.remove(c.id)}>×</button>
      </div>
    {/each}
  </aside>

  <section class="card convo">
    {#if !chat.activeId && chat.messages.length === 0}
      <p class="muted">Ask about your recovery data — trends, flare-ups, comparisons.</p>
    {/if}
    <div class="messages">
      {#each chat.messages as m}
        <div class="msg {m.role}">
          <div class="bubble">{m.content}</div>
        </div>
      {/each}
      {#if chat.tool}
        <div class="msg assistant">
          <div class="bubble muted small">Looking at your data… ({chat.tool})</div>
        </div>
      {/if}
      {#if chat.streaming}
        <div class="msg assistant"><div class="bubble">{chat.streaming}</div></div>
      {/if}
    </div>
    {#if chat.error}<p class="error small">{chat.error}</p>{/if}
    <form class="composer" onsubmit={submit}>
      <input placeholder="Ask anything…" bind:value={draft} disabled={chat.sending} />
      <button type="submit" disabled={chat.sending || !draft.trim()}>Send</button>
    </form>
  </section>
</div>

<style>
  .chat-layout {
    display: grid;
    grid-template-columns: 220px 1fr;
    gap: 1rem;
    align-items: start;
  }
  .threads {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
  }
  .newchat {
    margin-bottom: 0.5rem;
  }
  .thread {
    display: flex;
    align-items: center;
    gap: 0.25rem;
  }
  .thread.sel {
    font-weight: 600;
  }
  .threadname {
    flex: 1;
    text-align: left;
    background: none;
    border: none;
    cursor: pointer;
    padding: 0.35rem;
    color: inherit;
  }
  .del {
    background: none;
    border: none;
    cursor: pointer;
    opacity: 0.5;
    color: inherit;
  }
  .convo {
    display: flex;
    flex-direction: column;
    min-height: 60vh;
  }
  .messages {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
    overflow-y: auto;
  }
  .msg {
    display: flex;
  }
  .msg.user {
    justify-content: flex-end;
  }
  .bubble {
    max-width: 80%;
    padding: 0.5rem 0.75rem;
    border-radius: 0.75rem;
    white-space: pre-wrap;
  }
  .msg.user .bubble {
    background: var(--accent-soft);
  }
  .msg.assistant .bubble {
    background: var(--surface-2);
  }
  .composer {
    display: flex;
    gap: 0.5rem;
    margin-top: 0.75rem;
  }
  .composer input {
    flex: 1;
  }
  @media (max-width: 640px) {
    .chat-layout {
      grid-template-columns: 1fr;
    }
  }
</style>
