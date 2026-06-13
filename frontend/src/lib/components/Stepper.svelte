<script lang="ts">
  // Numeric stepper supporting half-points, with a null/"unset" state.
  let {
    value = $bindable<number | null>(null),
    min = 0,
    max = 10,
    step = 0.5,
    label = '',
    onChange
  }: {
    value: number | null;
    min?: number;
    max?: number;
    step?: number;
    label?: string;
    onChange?: () => void;
  } = $props();

  function clamp(n: number): number {
    return Math.min(max, Math.max(min, Math.round(n / step) * step));
  }
  function bump(delta: number) {
    const base = value ?? min;
    value = clamp(base + delta);
    onChange?.();
  }
  function clear() {
    value = null;
    onChange?.();
  }
</script>

<div class="stepper">
  {#if label}<label>{label}</label>{/if}
  <div class="controls">
    <button type="button" onclick={() => bump(-step)} aria-label="decrease">−</button>
    <span class="value" class:unset={value == null}>{value == null ? '—' : value}</span>
    <button type="button" onclick={() => bump(step)} aria-label="increase">+</button>
    {#if value != null}
      <button type="button" class="clear" onclick={clear} aria-label="clear">✕</button>
    {/if}
  </div>
</div>

<style>
  .controls {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  .value {
    min-width: 2.5rem;
    text-align: center;
    font-variant-numeric: tabular-nums;
    font-size: 1.1rem;
  }
  .value.unset {
    color: var(--muted);
  }
  .clear {
    padding: 0.3rem 0.5rem;
    font-size: 0.8rem;
  }
  button {
    min-width: 2.4rem;
  }
</style>
