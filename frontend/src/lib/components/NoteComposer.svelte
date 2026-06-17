<script lang="ts">
  import { api } from '$lib/api';
  import { combineDateTimeToISO, defaultJabTime, todayISO } from '$lib/time';

  let { date, onAdded }: { date: string; onAdded: () => void } = $props();

  let body = $state('');
  let timeOpen = $state(false);
  let time = $state('');
  let submitting = $state(false);
  const defaultTime = $derived(defaultJabTime(date));

  async function submit() {
    const text = body.trim();
    if (!text || submitting) return;
    submitting = true;
    try {
      const sendTime = timeOpen || date !== todayISO();
      const hhmm = time || defaultTime;
      await api.addNote(date, {
        body: text,
        occurred_at: sendTime ? combineDateTimeToISO(date, hhmm) : undefined
      });
      body = '';
      time = '';
      timeOpen = false;
      onAdded();
    } finally {
      submitting = false;
    }
  }
</script>

<div class="card">
  <label for="note-body">Add a note</label>
  <textarea
    id="note-body"
    bind:value={body}
    placeholder="What's happening? Pain, activity, what helped…"
    rows="3"
  ></textarea>
  <div class="note-actions">
    {#if timeOpen}
      <span class="time">
        <label for="note-time">Time</label>
        <input id="note-time" type="time" bind:value={time} />
      </span>
    {:else}
      <button
        class="link"
        onclick={() => {
          time = defaultTime;
          timeOpen = true;
        }}>🕑 {defaultTime} · change time</button
      >
    {/if}
    <button class="status-G" onclick={submit} disabled={!body.trim() || submitting}>
      Add note
    </button>
  </div>
</div>

<style>
  textarea {
    width: 100%;
    box-sizing: border-box;
    margin-top: 0.4rem;
  }
  .note-actions {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    margin-top: 0.6rem;
  }
  .time {
    display: flex;
    align-items: center;
    gap: 0.4rem;
  }
  .time label {
    margin: 0;
  }
  .link {
    border: none;
    background: none;
    color: var(--text-muted);
    padding: 0;
    font-size: 0.85rem;
  }
</style>
