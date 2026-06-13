<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '$lib/api';
  import LineChart from '$lib/components/LineChart.svelte';
  import { shiftISODate, todayISO } from '$lib/time';
  import type { DailyEntrySummary, DailyStatPoint } from '$lib/types';

  let rangeDays = $state(30);
  let entries = $state<DailyEntrySummary[]>([]);
  let stats = $state<DailyStatPoint[]>([]);

  async function load() {
    const to = todayISO();
    const from = shiftISODate(to, -rangeDays);
    [entries, stats] = await Promise.all([api.listEntries(from, to), api.dailyStats(from, to)]);
  }

  onMount(load);
  $effect(() => {
    void rangeDays;
    load();
  });

  const labels = $derived(stats.map((s) => s.entry_date.slice(5)));

  function ds(label: string, key: keyof DailyStatPoint, color: string) {
    return {
      label,
      data: stats.map((s) => s[key] as number | null),
      borderColor: color,
      backgroundColor: color,
      tension: 0.25,
      spanGaps: true
    };
  }

  const painDatasets = $derived([
    ds('Sharp pain episodes', 'sharp_pain_episodes', '#e8505b'),
    ds('Worst pain', 'worst_pain', '#f5a623'),
    ds('Tingling level', 'tingling_level', '#4f8cff'),
    ds('Session intensity', 'session_intensity', '#2ec27e')
  ]);

  const postureDatasets = $derived([
    {
      label: 'Sitting (min)',
      data: stats.map((s) => s.sitting_minutes),
      backgroundColor: '#e8505b'
    },
    {
      label: 'Standing (min)',
      data: stats.map((s) => s.standing_minutes),
      backgroundColor: '#2ec27e'
    }
  ]);

  const statusClass: Record<string, string> = { G: 'status-G', A: 'status-A', R: 'status-R' };
</script>

<div class="card">
  <div class="row" style="align-items: center; justify-content: space-between">
    <h2 style="margin: 0">History</h2>
    <select bind:value={rangeDays} style="width: auto">
      <option value={30}>Last 30 days</option>
      <option value={90}>Last 90 days</option>
    </select>
  </div>
</div>

<div class="card">
  <h3 style="margin-top: 0">Pain & tingling</h3>
  <LineChart {labels} datasets={painDatasets} />
</div>

<div class="card">
  <h3 style="margin-top: 0">Sitting vs standing (minutes/day)</h3>
  <LineChart {labels} datasets={postureDatasets} type="bar" />
</div>

<div class="card">
  <h3 style="margin-top: 0">Entries</h3>
  <table>
    <thead>
      <tr
        ><th>Date</th><th>Status</th><th>Episodes</th><th>Worst</th><th>Tingling</th><th>Sleep</th
        ></tr
      >
    </thead>
    <tbody>
      {#each entries as e}
        <tr>
          <td><a href={`/?date=${e.entry_date}`}>{e.entry_date}</a></td>
          <td
            >{#if e.status}<span class="pill {statusClass[e.status]}">{e.status}</span
              >{:else}—{/if}</td
          >
          <td>{e.sharp_pain_episodes}</td>
          <td>{e.worst_pain ?? '—'}</td>
          <td>{e.tingling_level ?? '—'}</td>
          <td>{e.sleep_quality ?? '—'}</td>
        </tr>
      {/each}
      {#if entries.length === 0}
        <tr><td colspan="6" class="muted">No entries in range.</td></tr>
      {/if}
    </tbody>
  </table>
</div>
