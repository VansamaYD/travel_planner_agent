import type { MessageArtifact } from '../../shared/api/conversations'

export function mergeGuideArtifacts(
  artifacts: MessageArtifact[],
  limit = 8,
): MessageArtifact | null {
  const unique = new Map<string, NonNullable<MessageArtifact['guides']>[number]>()
  for (const artifact of artifacts) {
    if (artifact.type !== 'guide_candidates') continue
    for (const guide of artifact.guides ?? []) {
      if (!unique.has(guide.candidate_id)) unique.set(guide.candidate_id, guide)
    }
  }
  if (!unique.size) return null
  return { type: 'guide_candidates', guides: [...unique.values()].slice(0, limit) }
}
