import { expect, test } from 'vitest'
import { useAnnotationStore } from './annotationStore'

test('a section rewrite removes its drafts without removing notes or other drafts', () => {
  const store = useAnnotationStore.getState()
  store.setEdit('r_rewrite', 'summary-p0', 'stale draft')
  store.setEdit('r_rewrite', 'summary-takeaway', 'old takeaway')
  store.setEdit('r_rewrite', 'summary-other-p0', 'other section')
  store.addHighlight('r_rewrite', { sectionId: 'summary', text: 'Reader note', color: 'sun', comment: 'Explain' })
  store.clearSectionEdits('r_rewrite', 'summary')
  const saved = useAnnotationStore.getState().annotations.r_rewrite
  expect(saved.edits).toEqual({ 'summary-other-p0': 'other section' })
  expect(saved.highlights).toHaveLength(1)
})
