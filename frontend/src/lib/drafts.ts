const KEY = 'vantage.v2.drafts'
export function clearLegacyStorage() {
  try {
    // A versioned marker prevents subsequent visits from deleting new data.
    if (!localStorage.getItem('vantage.schema.v2')) {
      localStorage.removeItem('vantage.annotations.v1')
      localStorage.removeItem('vantage.knowledge.v1')
      localStorage.setItem('vantage.schema.v2', '1')
    }
  } catch { /* Storage can be unavailable; server versions remain authoritative. */ }
}
export function loadDraft(report: string, base: string): Record<string, string> {
  try { return JSON.parse(localStorage.getItem(KEY) || '{}')[report + ':' + base] || {} } catch { return {} }
}
export function saveDraft(report: string, base: string, edits: Record<string, string>) {
  try {
    const all = JSON.parse(localStorage.getItem(KEY) || '{}')
    if (Object.keys(edits).length) all[report + ':' + base] = edits
    else delete all[report + ':' + base]
    localStorage.setItem(KEY, JSON.stringify(all))
  } catch { /* The current unsaved text remains in memory. */ }
}
