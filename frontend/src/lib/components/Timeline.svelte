<script lang="ts">
  import { api } from '$lib/api';
  import { buildTimeline, type TimelineEvent } from '$lib/timeline';
  import { combineDateTimeToISO, formatMinutesish, POSTURE_LABEL } from '$lib/time';
  import type { DailyEntry } from '$lib/types';

  let { entry, date, onChanged }: { entry: DailyEntry; date: string; onChanged: () => void } =
    $props();

  const events = $derived(buildTimeline(entry));

  let editingId = $state<string | null>(null);
  let editBody = $state('');
  let editTime = $state('');

  function fmtTime(iso: string): string {
    return new Date(iso + 'Z').toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  const POSTURE_ICON: Record<string, string> = {
    sitting: '🪑',
    standing: '🧍',
    lying: '🛏️',
    walking: '🚶'
  };

  function dotClass(kind: TimelineEvent['kind']): string {
    return `dot-${kind}`;
  }

  function startEdit(ev: Extract<TimelineEvent, { kind: 'note' }>) {
    editingId = ev.id;
    editBody = ev.body;
    const d = new Date(ev.at + 'Z');
    editTime = `${d.getHours().toString().padStart(2, '0')}:${d
      .getMinutes()
      .toString()
      .padStart(2, '0')}`;
  }

  async function saveEdit(id: string) {
    await api.updateNote(id, {
      body: editBody.trim(),
      occurred_at: combineDateTimeToISO(date, editTime)
    });
    editingId = null;
    onChanged();
  }

  async function removeNote(id: string) {
    await api.deleteNote(id);
    onChanged();
  }
</script>

<div class="card">
  <h3 class="tl-title">Timeline</h3>
  {#if events.length === 0}
    <p class="muted small">Nothing logged yet today.</p>
  {:else}
    <div class="rail">
      {#each events as ev}
        <div class="rail-item">
          <span class="rail-dot {dotClass(ev.kind)}"></span>
          <div class="rail-card">
            {#if ev.kind === 'timer'}
              <div class="rail-top">
                <span>{POSTURE_ICON[ev.posture]} {POSTURE_LABEL[ev.posture]}</span>
                <span class="rail-time">{fmtTime(ev.at)}</span>
              </div>
              <div class="rail-sub">
                {ev.running ? 'ongoing' : formatMinutesish(ev.durationSeconds ?? 0)}
              </div>
              {#if ev.label?.trim()}<div class="rail-sub">{ev.label}</div>{/if}
            {:else if ev.kind === 'pain'}
              <div class="rail-top">
                <span>⚡ Pain jab{ev.level != null ? ` · level ${ev.level}` : ''}</span>
                <span class="rail-time">{fmtTime(ev.at)}</span>
              </div>
              {#if ev.context}<div class="rail-sub">{ev.context}</div>{/if}
            {:else if ev.kind === 'check'}
              <div class="rail-top">
                <span>✓ {ev.label}</span>
                <span class="rail-time">{fmtTime(ev.at)}</span>
              </div>
            {:else if ev.kind === 'note'}
              {#if editingId === ev.id}
                <textarea bind:value={editBody} rows="2"></textarea>
                <div class="edit-row">
                  <input type="time" bind:value={editTime} />
                  <span>
                    <button class="link" onclick={() => (editingId = null)}>cancel</button>
                    <button class="link" onclick={() => saveEdit(ev.id)} disabled={!editBody.trim()}
                      >save</button
                    >
                  </span>
                </div>
              {:else}
                <div class="rail-top">
                  <span>✎ Note</span>
                  <span class="rail-time">{fmtTime(ev.at)}</span>
                </div>
                <div class="rail-sub">{ev.body}</div>
                <div class="note-edit">
                  <button class="link" onclick={() => startEdit(ev)}>edit</button>
                  <button class="link" onclick={() => removeNote(ev.id)}>remove</button>
                </div>
              {/if}
            {/if}
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .tl-title {
    margin: 0 0 0.9rem;
    font-size: 1rem;
  }
  .rail {
    position: relative;
    padding-left: 1.4rem;
  }
  .rail::before {
    content: '';
    position: absolute;
    left: 0.42rem;
    top: 0.3rem;
    bottom: 0.3rem;
    width: 2px;
    background: var(--border);
  }
  .rail-item {
    position: relative;
    padding: 0.4rem 0 0.55rem;
  }
  .rail-dot {
    position: absolute;
    left: -1.16rem;
    top: 0.6rem;
    width: 0.62rem;
    height: 0.62rem;
    border-radius: 50%;
    border: 2px solid var(--bg);
  }
  .dot-timer {
    background: #5b8fb0;
  }
  .dot-pain {
    background: #c0563f;
  }
  .dot-check {
    background: #6a9a5b;
  }
  .dot-note {
    background: #9a7bb5;
  }
  .rail-card {
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: 9px;
    padding: 0.5rem 0.65rem;
  }
  .rail-top {
    display: flex;
    justify-content: space-between;
    gap: 0.5rem;
    font-size: 0.85rem;
  }
  .rail-time {
    color: var(--text-muted);
    font-size: 0.78rem;
    white-space: nowrap;
  }
  .rail-sub {
    color: var(--text-muted);
    font-size: 0.8rem;
    margin-top: 0.15rem;
  }
  .note-edit,
  .edit-row {
    display: flex;
    justify-content: flex-end;
    gap: 0.6rem;
    margin-top: 0.35rem;
  }
  .edit-row {
    justify-content: space-between;
    align-items: center;
  }
  textarea {
    width: 100%;
    box-sizing: border-box;
  }
  .link {
    border: none;
    background: none;
    color: var(--text-muted);
    padding: 0;
    font-size: 0.8rem;
  }
</style>
