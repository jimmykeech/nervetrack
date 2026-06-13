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

  function token(name: string): string {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || '#888';
  }

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
          x: { ticks: { color: token('--text-muted'), maxRotation: 0, autoSkip: true } },
          y: { ticks: { color: token('--text-muted') }, grid: { color: token('--border') } }
        },
        plugins: {
          legend: { labels: { color: token('--text') } }
        }
      }
    });
  }

  let observer: MutationObserver | null = null;

  onMount(() => {
    render();
    // Re-render when the theme flips so axes/legend recolour for the new mode.
    observer = new MutationObserver(render);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme']
    });
  });
  onDestroy(() => {
    observer?.disconnect();
    chart?.destroy();
  });

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
