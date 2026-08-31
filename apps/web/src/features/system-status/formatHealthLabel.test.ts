import { describe, expect, it } from 'vitest'

import { formatHealthLabel } from './formatHealthLabel'

describe('formatHealthLabel', () => {
  it('formats known checks', () => {
    expect(formatHealthLabel('database')).toBe('数据库')
  })

  it('keeps unknown checks visible', () => {
    expect(formatHealthLabel('future_provider')).toBe('future_provider')
  })
})
