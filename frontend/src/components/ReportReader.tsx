import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { BookOpen, Highlighter, MessageSquarePlus, X, Trash2 } from 'lucide-react'
import type { Anchor, Annotation, Content, HighlightColor, Item } from '../types'
import { addAnnotation, fetchAnnotations, patchAnnotation, removeAnnotation } from '../lib/api'
import { highlightedSegments, resolveSelection } from '../lib/selection'
import { EvidenceCard } from './Research'
import { ReaderContext, useReader } from '../lib/readerContext'

const colors: { key: HighlightColor; label: string }[] = [{ key: 'sun', label: 'Important' }, { key: 'ok', label: 'Agree' }, { key: 'risk', label: 'Questionable' }, { key: 'info', label: 'Follow up' }]
const scrollBehavior = (): ScrollBehavior => window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'

export function CitedText({ item, text }: { item: Item; text: string }) {
  const reader = useReader()
  const marks = reader?.notes.filter(n => n.anchor_status === 'active').flatMap(n => n.anchors.filter(a => a.item_id === item.id && text.slice(a.start,a.end) === a.quote).map(a => ({ ...a, id: n.annotation_id, color: n.color }))) || []
  return <><p className="item-text" data-item-text={item.id}>{highlightedSegments(text, marks).map(s => s.ids.length ? <mark key={s.start} className={'highlight hl-' + s.color} data-highlight-ids={s.ids.join(' ')}>{s.text}</mark> : <span key={s.start}>{s.text}</span>)}</p>{reader && item.citations.length > 0 && <span className="inline-citations" aria-label="Citations">{[...new Set(item.citations.map(c => c.evidence_id))].map(id => <button type="button" key={id} className="citation-chip" aria-label={'Show source ' + (reader.content.evidence.findIndex(e => e.evidence_id === id)+1)} onClick={() => reader.source([id])}>[{reader.content.evidence.findIndex(e => e.evidence_id === id)+1}]</button>)}</span>}</>
}
type NoteDraft = { anchors: Anchor[]; color: HighlightColor; comment: string; existing?: Annotation }
export function ReportReader({ reportId, versionId, content, canAnnotate, editing, onError, onFollowup, onSavingChange, children }: { reportId: string; versionId: string; content: Content; canAnnotate: boolean; editing: boolean; onError: (text: string) => void; onFollowup: (item: Item, selected: string) => void; onSavingChange: (saving: boolean) => void; children: ReactNode }) {
  const annotationsEnabled = canAnnotate && !editing
  const [notes, setNotes] = useState<Annotation[]>([]), [drawer, setDrawer] = useState(false), [activeSources, setActiveSources] = useState<string[]>([]), [sidebarTab, setSidebarTab] = useState('sources')
  const [selection, setSelection] = useState<{ anchors: Anchor[]; x: number; y: number } | null>(null), [saving, setSaving] = useState(false), [noteError, setNoteError] = useState('')
  const draftKey = 'vantage.annotation.draft.' + reportId + ':' + versionId
  const [draft, setDraft] = useState<NoteDraft | null>(() => { try { return JSON.parse(localStorage.getItem(draftKey) || 'null') } catch { return null } })
  const root = useRef<HTMLDivElement>(null), panel = useRef<HTMLElement>(null)
  useEffect(() => { let active = true; void fetchAnnotations(reportId, versionId).then(n => { if (active) setNotes(n) }).catch(e => onError(e.message)); return () => { active = false } }, [reportId, versionId, onError])
  useEffect(() => { try { if (draft) localStorage.setItem(draftKey, JSON.stringify(draft)); else localStorage.removeItem(draftKey) } catch { /* Retain the draft in memory. */ } }, [draft, draftKey])
  useEffect(() => {
    if (!annotationsEnabled) return
    let frame = 0
    function read() {
      const s = window.getSelection()
      if (!root.current || !s || !s.rangeCount || s.isCollapsed) { setSelection(null); return }
      const range = s.getRangeAt(0)
      if (!root.current.contains(range.startContainer) || !root.current.contains(range.endContainer)) { setSelection(null); return }
      const anchors = resolveSelection(root.current, range)
      if (!anchors.length) { setSelection(null); return }
      const rect = range.getBoundingClientRect()
      setSelection({ anchors, x: Math.max(12, Math.min(window.innerWidth-310, rect.left)), y: Math.max(12, rect.top-48) })
    }
    function schedule() { cancelAnimationFrame(frame); frame = requestAnimationFrame(read) }
    document.addEventListener('selectionchange', schedule); document.addEventListener('pointerup', schedule); document.addEventListener('keyup', schedule)
    return () => { cancelAnimationFrame(frame); document.removeEventListener('selectionchange', schedule); document.removeEventListener('pointerup', schedule); document.removeEventListener('keyup', schedule) }
  }, [annotationsEnabled])
  function source(ids: string[]) {
    setDrawer(true); setSidebarTab('sources'); setActiveSources(ids)
    requestAnimationFrame(() => requestAnimationFrame(() => {
      const node = panel.current?.querySelector<HTMLAnchorElement>('[data-evidence-id="' + CSS.escape(ids[0]) + '"]')
      if (node) { node.scrollIntoView({ behavior: scrollBehavior(), block: 'center' }); node.focus({ preventScroll: true }) }
    }))
  }
  async function saveNote(value: NoteDraft) {
    if (saving || !annotationsEnabled) return
    setSaving(true); onSavingChange(true); setDraft(value); setNoteError('')
    try {
      if (value.existing) await patchAnnotation(reportId, value.existing, { color: value.color, comment: value.comment })
      else await addAnnotation(reportId, versionId, value.anchors, value.color, value.comment)
      setNotes(await fetchAnnotations(reportId, versionId)); setSidebarTab('notes'); setDraft(null); setSelection(null); window.getSelection()?.removeAllRanges()
    } catch (e) { const message = (e as Error).message + ' Your annotation draft has been kept.'; setNoteError(message); onError(message) } finally { setSaving(false); onSavingChange(false) }
  }
  async function erase(note: Annotation) {
    if (saving || !annotationsEnabled) return
    setSaving(true); onSavingChange(true)
    try { await removeAnnotation(reportId, note); setNotes(n => n.filter(x => x.annotation_id !== note.annotation_id)) } catch (e) { onError((e as Error).message) } finally { setSaving(false); onSavingChange(false) }
  }
  function jump(note: Annotation) {
    const item = root.current?.querySelector<HTMLElement>('[data-item-text="' + CSS.escape(note.anchors[0].item_id) + '"]')
    const mark = root.current?.querySelector<HTMLElement>('[data-highlight-ids~="' + CSS.escape(note.annotation_id) + '"]')
    ;(mark || item)?.scrollIntoView({ behavior: scrollBehavior(), block: 'center' })
    if (window.innerWidth < 1200) setDrawer(false)
  }
  return <ReaderContext.Provider value={{ notes, content, source }}><div className="report-reader" ref={root}>
    <div className="report-body">{children}</div>
    <button className="sources-toggle button secondary" onClick={() => setDrawer(true)}><BookOpen size={16} />Sources & notes</button>
    {drawer && <button className="source-scrim" aria-label="Close sources drawer" onClick={() => setDrawer(false)} />}
    <aside className={'sources-panel ' + (drawer ? 'drawer-open' : '')} ref={panel} aria-label="Sources and notes">
      <header><BookOpen size={17} /><h2>Sources & notes</h2><button className="icon-button mobile-source-close" aria-label="Close sources" onClick={() => setDrawer(false)}><X size={18} /></button></header>
      <div className="source-tabs" role="tablist" aria-label="Sources and notes tabs"><button role="tab" aria-selected={sidebarTab === 'sources'} onClick={() => setSidebarTab('sources')}>Sources ({content.evidence.length})</button><button role="tab" aria-selected={sidebarTab === 'notes'} onClick={() => setSidebarTab('notes')}>Notes ({notes.length})</button></div><div className="sources-scroll"><section hidden={sidebarTab !== 'sources'}><h3>Sources ({content.evidence.length})</h3>{content.evidence.map((ev,index) => <EvidenceCard evidence={ev} index={index} active={activeSources.includes(ev.evidence_id)} key={ev.evidence_id} />)}</section>
      <section className="reader-notes" hidden={sidebarTab !== 'notes'}><h3>Notes ({notes.length})</h3>{!notes.length && <p className="muted text-sm">{!canAnnotate ? 'No notes in this version.' : editing ? 'Return to read only to highlight a passage or add a note.' : 'Select a passage to highlight it or add a note.'}</p>}{notes.map(note => <article className={'reader-note hl-' + note.color} key={note.annotation_id}><button className="note-quote" disabled={editing} onClick={() => jump(note)}>{note.anchors.map(a => a.quote).join(' … ')}</button><p>{note.comment}</p>{note.anchor_status === 'unanchored' && <p className="note-unanchored">Original passage changed. Note retained.</p>}<span className="muted text-sm">{colors.find(c => c.key === note.color)?.label}</span>{annotationsEnabled && <div className="item-actions"><button className="text-button" disabled={saving} onClick={() => setDraft({ anchors: note.anchors, color: note.color, comment: note.comment, existing: note })}>Edit note</button><button className="icon-button" disabled={saving} aria-label="Delete note" onClick={() => void erase(note)}><Trash2 size={13} /></button></div>}</article>)}</section></div>
    </aside>
    {annotationsEnabled && !draft && selection && <div className="selection-toolbar" role="toolbar" aria-label="Selected passage tools" style={{ left: selection.x, top: selection.y }} onPointerDown={e => e.preventDefault()}><Highlighter size={14} />{colors.map(c => <button key={c.key} aria-label={'Highlight as ' + c.label} title={c.label} className={'color-dot hl-' + c.key} disabled={saving} onClick={() => void saveNote({ anchors: selection.anchors, color: c.key, comment: '' })} />)}<button aria-label="Add a note" className="icon-button" disabled={saving} onClick={() => { setDraft({ anchors: selection.anchors, color: 'sun', comment: '' }); setSelection(null) }}><MessageSquarePlus size={16} /></button><button className="text-button" disabled={saving} onClick={() => { const a = selection.anchors[0], item = [...content.comparison,...content.brief,...content.changes].find(i => i.id === a.item_id); if (item) onFollowup(item, a.quote); setSelection(null); window.getSelection()?.removeAllRanges() }}>Follow up</button></div>}
    {annotationsEnabled && draft && <div className="modal-backdrop"><section className="panel annotation-modal" role="dialog" aria-modal="true" aria-labelledby="note-heading"><h2 id="note-heading">{draft.existing ? 'Edit note' : 'Save a passage note'}</h2><blockquote>{draft.anchors.map(a => a.quote).join(' … ')}</blockquote><div className="choice-chips">{colors.map(c => <button key={c.key} disabled={saving} aria-pressed={draft.color === c.key} className={draft.color === c.key ? 'selected' : ''} onClick={() => setDraft({ ...draft, color: c.key })}>{c.label}</button>)}</div>{noteError && <p className="notice error" role="alert">{noteError}</p>}<label>Note<textarea aria-label="Passage note" rows={4} disabled={saving} value={draft.comment} onChange={e => setDraft({ ...draft, comment: e.target.value })} /></label><div className="button-row"><button className="button primary" disabled={saving} onClick={() => void saveNote(draft)}>{saving ? 'Saving…' : 'Save note'}</button><button className="button secondary" disabled={saving} onClick={() => setDraft(null)}>Discard note draft</button></div></section></div>}
  </div></ReaderContext.Provider>
}
