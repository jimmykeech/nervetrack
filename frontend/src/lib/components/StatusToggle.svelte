<script lang="ts">
  import type { Status } from '$lib/types';

  let {
    value = $bindable<Status | null>(null),
    onChange
  }: { value: Status | null; onChange?: () => void } = $props();

  const options: { key: Status; label: string }[] = [
    { key: 'G', label: 'Green' },
    { key: 'A', label: 'Amber' },
    { key: 'R', label: 'Red' }
  ];

  function pick(s: Status) {
    value = value === s ? null : s;
    onChange?.();
  }
</script>

<div class="toggle">
  {#each options as opt}
    <button
      type="button"
      class="opt {value === opt.key ? `status-${opt.key} on` : ''}"
      onclick={() => pick(opt.key)}
    >
      {opt.label}
    </button>
  {/each}
</div>

<style>
  .toggle {
    display: flex;
    gap: 0.5rem;
  }
  .opt {
    flex: 1;
    font-weight: 600;
  }
  .opt.on {
    transform: translateY(-1px);
  }
</style>
