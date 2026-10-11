import { createContext, useContext } from 'react'
import type { Annotation, Content } from '../types'
export const ReaderContext = createContext<{ notes: Annotation[]; content: Content; source: (ids: string[]) => void } | null>(null)
export const useReader = () => useContext(ReaderContext)
