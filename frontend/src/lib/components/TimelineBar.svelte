<script lang="ts">
  import type { Interval, TinglingInterval } from '$lib/types';
  import { postureSegments, tinglingSegments, nowPct, localDayStartMs } from '$lib/timelineBar';
  import { postureColor } from '$lib/posture';
  import { POSTURE_LABEL, POSTURES, todayISO } from '$lib/time';

  let {
    intervals,
    tingling,
    date,
    now
  }: { intervals: Interval[]; tingling: TinglingInterval[]; date: string; now: number } = $props();

  const dayStart = $derived(localDayStartMs(date));
  const pSegs = $derived(postureSegments(intervals, dayStart, now));
  const tSegs = $derived(tinglingSegments(tingling, dayStart, now));
  const isToday = $derived(date === todayISO());
  const nowLeft = $derived(nowPct(dayStart, now));
  const hasTingling = $derived(tSegs.length > 0);

  const TICKS = [
    { pct: 0, label: '12a', cls: 'first' },
    { pct: 25, label: '6a', cls: '' },
    { pct: 50, label: '12p', cls: '' },
    { pct: 75, label: '6p', cls: '' },
    { pct: 100, label: '12a', cls: 'last' }
  ];

  function fmtMs(ms: number): string {
    return new Date(ms).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }
</script>

<div class="tl">
  <div class="tl-caps">{isToday ? 'Timeline · today' : `Timeline · ${date}`}</div>

  <div class="tl-body">
    <div class="pbar">
      {#each pSegs as s (s.startMs)}
        <div
          class="pseg"
          style="left:{s.leftPct}%; width:{s.widthPct}%; background:{postureColor(s.posture)}"
          title="{POSTURE_LABEL[s.posture]} {fmtMs(s.startMs)}–{fmtMs(s.endMs)}"
        ></div>
      {/each}
    </div>
    {#if isToday}<div class="nowline" style="left:{nowLeft}%"></div>{/if}
  </div>

  <div class="tstrip">
    {#each tSegs as s (s.startMs)}
      <div
        class="tseg"
        style="left:{s.leftPct}%; width:{s.widthPct}%"
        title="Tingling level {s.level} · {fmtMs(s.startMs)}–{fmtMs(s.endMs)}"
      ></div>
    {/each}
  </div>

  <div class="axis">
    {#each TICKS as t}<div class="tick {t.cls}" style="left:{t.pct}%">{t.label}</div>{/each}
  </div>

  <div class="tl-legend">
    {#each POSTURES as p}
      <span><i style="background:{postureColor(p)}"></i>{POSTURE_LABEL[p]}</span>
    {/each}
    {#if hasTingling}<span><i style="background:var(--tingle)"></i>Tingling</span>{/if}
  </div>
</div>

<style>
  .tl {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  .tl-caps {
    text-transform: uppercase;
    letter-spacing: 0.09em;
    font-size: 0.72rem;
    color: var(--text-muted);
    font-weight: 700;
  }
  .tl-body {
    position: relative;
  }
  .pbar {
    position: relative;
    width: 100%;
    height: 15px;
    border-radius: var(--r-sm);
    overflow: hidden;
    background: var(--surface-2);
  }
  .pseg {
    position: absolute;
    top: 0;
    bottom: 0;
  }
  .tstrip {
    position: relative;
    width: 100%;
    height: 9px;
    border-radius: var(--r-sm);
    background: var(--surface-2);
    overflow: hidden;
  }
  .tseg {
    position: absolute;
    top: 0;
    bottom: 0;
    background: var(--tingle);
    border-radius: 3px;
  }
  .nowline {
    position: absolute;
    top: -3px;
    bottom: -3px;
    width: 2px;
    background: var(--accent);
  }
  .axis {
    position: relative;
    height: 1rem;
  }
  .tick {
    position: absolute;
    top: 0;
    font-size: 0.66rem;
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
    transform: translateX(-50%);
  }
  .tick.first {
    transform: none;
  }
  .tick.last {
    transform: translateX(-100%);
  }
  .tl-legend {
    display: flex;
    flex-wrap: wrap;
    gap: 0.35rem 0.9rem;
    font-size: 0.74rem;
    color: var(--text-muted);
  }
  .tl-legend span {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
  }
  .tl-legend i {
    width: 0.65rem;
    height: 0.65rem;
    border-radius: 3px;
    display: inline-block;
  }
</style>
