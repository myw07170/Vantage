import { describe, expect, it } from 'vitest'
import type { ClarifyQuestion } from '../types'
import { clarificationAnswers, hasSelectedProducts, questionOptionGroups } from './clarification'

const question: ClarifyQuestion = {
  id: 'products', type: 'multi', question: 'Which products?',
  options: ['Claude Code', 'Codex', 'Aider'],
  defaultSelected: ['Claude Code', 'Codex'],
}

describe('product confirmation', () => {
  it('selects requested products and leaves recommendations optional', () => {
    const answers = clarificationAnswers([question])
    expect(answers.products).toEqual(['Claude Code', 'Codex'])
    expect(hasSelectedProducts(answers)).toBe(true)
    expect(questionOptionGroups(question)).toEqual([
      { label: 'Products from your request', options: ['Claude Code', 'Codex'] },
      { label: 'Optional additions', options: ['Aider'] },
    ])
  })

  it('restores additions and removals without reselecting defaults', () => {
    const saved = { products: ['Codex', 'Custom Product'], focus: ['Pricing strategy'] }
    expect(clarificationAnswers([question], saved)).toEqual(saved)
    expect(questionOptionGroups(question, saved.products)[1].options).toEqual(['Aider', 'Custom Product'])
    expect(question.options).not.toContain('Custom Product')
  })

  it('preserves an explicitly empty selection on reload and prevents starting', () => {
    const restored = clarificationAnswers([question], { products: [] })
    expect(restored.products).toEqual([])
    expect(hasSelectedProducts(restored)).toBe(false)
    expect(hasSelectedProducts({ products: ['  '] })).toBe(false)
    expect(hasSelectedProducts({})).toBe(false)
  })

  it('allows manual selection after failed identification or category-only input', () => {
    const empty = { ...question, options: [], defaultSelected: [] }
    expect(hasSelectedProducts(clarificationAnswers([empty]))).toBe(false)
    const saved = { products: ['My Product'] }
    expect(hasSelectedProducts(clarificationAnswers([empty], saved))).toBe(true)
    expect(questionOptionGroups(empty, saved.products)).toEqual([
      { label: 'Optional additions', options: ['My Product'] },
    ])
  })
})
