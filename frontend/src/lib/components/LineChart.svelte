<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import {
    Chart,
    LineController,
    BarController,
    LineElement,
    BarElement,
    PointElement,
    LinearScale,
    CategoryScale,
    Tooltip,
    Legend
  } from 'chart.js';

  Chart.register(
    LineController,
    BarController,
    LineElement,
    BarElement,
    PointElement,
    LinearScale,
    CategoryScale,
    Tooltip,
    Legend
  );

  let {
    labels,
    datasets,
    type = 'line',
    height = 220
  }: {
    labels: string[];
    datasets: Record<string, unknown>[];
    type?: 'line' | 'bar';
    height?: number;
  } = $props();

  let canvas: HTMLCanvasElement;
  let chart: Chart | null = null;

  function render() {
    if (!canvas) return;
    chart?.destroy();
    chart = new Chart(canvas, {
      type: type as 'line',
      data: { labels, datasets: datasets as never },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        scales: {
          x: { ticks: { color: '#93a1b5', maxRotation: 0, autoSkip: true } },
          y: { ticks: { color: '#93a1b5' }, grid: { color: '#2e3a4d' } }
        },
        plugins: {
          legend: { labels: { color: '#e6ebf2' } }
        }
      }
    });
  }

  onMount(render);
  onDestroy(() => chart?.destroy());

  // Re-render when inputs change.
  $effect(() => {
    void labels;
    void datasets;
    render();
  });
</script>

<div style="height: {height}px">
  <canvas bind:this={canvas}></canvas>
</div>
