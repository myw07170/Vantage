import { expect, it } from 'vitest'
import { highlightedSegments } from './selection'

it('uses UTF-16 offsets without splitting emoji', () => {
  const text = 'Hello 😀 repeated repeated'
  const segments = highlightedSegments(text, [{ start: 6, end: 8, color: 'sun', id: 'emoji' }])
  expect(segments.map(s => s.text).join('')).toBe(text)
  expect(segments.find(s => s.color)?.text).toBe('😀')
})
it('anchors repeated phrases by offsets and retains overlapping notes', () => {
  const result = highlightedSegments('repeat repeat', [{ start: 7, end: 13, color: 'ok', id: 'second' }, { start: 9, end: 12, color: 'risk', id: 'overlap' }])
  expect(result[0].ids).toEqual([])
  expect(result.find(s => s.start === 9)?.ids).toEqual(['second', 'overlap'])
  expect(result.map(s => s.text).join('')).toBe('repeat repeat')
})
