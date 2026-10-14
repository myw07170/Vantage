import type { ClarifyQuestion, TaskDetail } from '../types'

/** Saved empty selections are intentional and must override recognition defaults. */
export function clarificationAnswers(
  questions: ClarifyQuestion[],
  saved: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    ...Object.fromEntries(questions
      .filter((q) => q.defaultSelected !== undefined)
      .map((q) => [q.id, [...q.defaultSelected!]])),
    ...saved,
  }
}

export function hasSelectedProducts(answers: Record<string, unknown>): boolean {
  return Array.isArray(answers.products)
    && answers.products.some((p) => typeof p === 'string' && p.trim().length > 0)
}

export function questionOptionGroups(q: ClarifyQuestion, selected: string[] = []) {
  const options = [...new Set([...(q.options ?? []), ...selected])]
  if (q.id !== 'products') return [{ label: '', options }]
  const requested = new Set(q.defaultSelected ?? [])
  return [
    { label: 'Products from your request', options: options.filter((p) => requested.has(p)) },
    { label: 'Optional additions', options: options.filter((p) => !requested.has(p)) },
  ].filter((group) => group.options.length > 0)
}

export function mergeProductInput(selected: string[], text: string): string[] {
  const seen = new Set<string>()
  return [...selected, ...text.split(/[,;，；\n]+/)]
    .map((value) => value.trim().replace(/\s+/g, ' '))
    .filter((value) => {
      if (!value || seen.has(value.toLowerCase())) return false
      seen.add(value.toLowerCase())
      return true
    })
}

export function draftKey(task: TaskDetail): string {
  return `vantage:clarification:${task.taskId}:${task.scopeRevision}:${task.clarificationRevision}:${task.clarificationStage}`
}

export function readDraft(task: TaskDetail): { answers?: Record<string, unknown>; text?: string } {
  try {
    const draft = JSON.parse(sessionStorage.getItem(draftKey(task)) ?? '{}')
    if (!draft || typeof draft !== 'object' || Array.isArray(draft)) return {}
    return {
      answers: draft.answers && typeof draft.answers === 'object' && !Array.isArray(draft.answers) ? draft.answers : undefined,
      text: typeof draft.text === 'string' ? draft.text : undefined,
    }
  }
  catch { return {} }
}

export function saveDraft(task: TaskDetail, answers: Record<string, unknown>, text: string) {
  try { sessionStorage.setItem(draftKey(task), JSON.stringify({ answers, text })) }
  catch { /* Browsing without storage still supports all server-saved answers. */ }
}
