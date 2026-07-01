// Records store: patient profile, conditions with lazily-loaded detail
// (notes + documents), and general (profile-level) documents.

import { api } from '$lib/api';
import { loadPainInstances } from '$lib/stores/painInstances.svelte';
import type { ConditionDetail, DocumentMeta, PainInstance, PatientProfile } from '$lib/types';

export function removeDoc(list: DocumentMeta[], id: string): DocumentMeta[] {
  return list.filter((d) => d.id !== id);
}

export class RecordsStore {
  profile = $state<PatientProfile | null>(null);
  conditions = $state<PainInstance[]>([]);
  details = $state<Record<string, ConditionDetail>>({});
  generalDocs = $state<DocumentMeta[]>([]);

  async load() {
    this.profile = await api.getProfile();
    this.conditions = await loadPainInstances();
    this.generalDocs = await api.listDocuments({ owner_type: 'profile' });
  }

  async saveProfile(patch: Partial<PatientProfile>) {
    this.profile = await api.saveProfile(patch);
  }

  async openCondition(id: string) {
    this.details = { ...this.details, [id]: await api.getCondition(id) };
  }

  async addNote(id: string, body: string) {
    await api.addConditionNote(id, { body });
    await this.openCondition(id);
  }

  async deleteNote(id: string, noteId: string) {
    await api.deleteConditionNote(noteId);
    await this.openCondition(id);
  }

  async uploadDoc(form: FormData, ownerType: string, instanceId?: string) {
    await api.uploadDocument(form);
    if (ownerType === 'condition' && instanceId) {
      await this.openCondition(instanceId);
    } else {
      this.generalDocs = await api.listDocuments({ owner_type: 'profile' });
    }
  }

  async deleteDoc(docId: string, instanceId?: string) {
    await api.deleteDocument(docId);
    if (instanceId) {
      await this.openCondition(instanceId);
    } else {
      this.generalDocs = removeDoc(this.generalDocs, docId);
    }
  }
}
