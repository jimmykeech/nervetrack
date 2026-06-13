<script lang="ts">
  import type { PostureTotals } from '$lib/types';
  import { ratioSegments } from '$lib/ratio';
  import { POSTURE_META, postureColor } from '$lib/posture';
  import { formatMinutesish, sitStandRatio } from '$lib/time';

  let { totals, showHeader = true }: { totals: PostureTotals; showHeader?: boolean } = $props();
  const segments = $derived(ratioSegments(totals));
</script>

<div class="ratiobar">
  {#if showHeader}
    <div class="label-caps">Posture today · sit : stand {sitStandRatio(totals)}</div>
  {/if}
  <div class="bar">
    {#each segments as s (s.posture)}
      <div
        class="seg"
        style="width:{s.percent}%; background:{postureColor(s.posture)}"
        title="{POSTURE_META[s.posture].label} {formatMinutesish(s.seconds)}"
      ></div>
    {/each}
    {#if segments.length === 0}<div class="seg empty"></div>{/if}
  </div>
  <div class="legend">
    <span class="sit tnum">Sitting {formatMinutesish(totals.sitting)}</span>
    <span class="stand tnum">Standing {formatMinutesish(totals.standing)}</span>
  </div>
</div>

<style>
  .ratiobar {
    display: flex;
    flex-direction: column;
    gap: 0.55rem;
  }
  .bar {
    display: flex;
    height: 10px;
    border-radius: var(--r-sm);
    overflow: hidden;
    background: var(--surface-2);
  }
  .seg {
    height: 100%;
  }
  .seg.empty {
    width: 100%;
    background: var(--surface-2);
  }
  .legend {
    display: flex;
    justify-content: space-between;
    font-size: 0.85rem;
  }
  .sit {
    color: var(--posture-sitting);
    font-weight: 600;
  }
  .stand {
    color: var(--posture-standing);
    font-weight: 600;
  }
</style>
