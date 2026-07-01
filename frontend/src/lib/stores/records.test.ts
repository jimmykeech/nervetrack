import { describe, expect, it } from 'vitest';
import { removeDoc } from './records.svelte';
import type { DocumentMeta } from '$lib/types';

const doc = (id: string): DocumentMeta => ({
  id,
  owner_type: 'profile',
  instance_id: null,
  title: id,
  notes: null,
  filename: null,
  mime_type: null,
  size_bytes: null,
  created_at: null
});

describe('removeDoc', () => {
  it('removes the matching document by id', () => {
    const list = [doc('a'), doc('b'), doc('c')];
    expect(removeDoc(list, 'b').map((d) => d.id)).toEqual(['a', 'c']);
  });
});
