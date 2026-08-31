import { describe, expect, it } from 'vitest'

import type { GuideCandidateArtifactItem, MessageArtifact } from '../../shared/api/conversations'
import { mergeGuideArtifacts } from './mergeGuideArtifacts'

function guide(candidate_id: string): GuideCandidateArtifactItem {
  return {
    candidate_id,
    title: candidate_id,
    author: '',
    summary: '',
    url: `https://example.com/${candidate_id}`,
    status: 'discovered',
  }
}

describe('mergeGuideArtifacts', () => {
  it('merges historical guide groups by candidate id and preserves first-seen order', () => {
    const artifacts: MessageArtifact[] = [
      { type: 'guide_candidates', guides: [guide('a'), guide('b')] },
      { type: 'guide_candidates', guides: [guide('b'), guide('c')] },
    ]

    const merged = mergeGuideArtifacts(artifacts)

    expect(merged?.guides?.map((item) => item.candidate_id)).toEqual(['a', 'b', 'c'])
  })

  it('caps legacy message cards to the display limit', () => {
    const artifacts: MessageArtifact[] = [
      { type: 'guide_candidates', guides: Array.from({ length: 12 }, (_, index) => guide(`${index}`)) },
    ]

    expect(mergeGuideArtifacts(artifacts)?.guides).toHaveLength(8)
  })
})
