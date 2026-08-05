import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { MotionConfig } from 'framer-motion'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {/* `reducedMotion="user"` drops transform and layout animation for anyone
        who has asked the OS for less motion, while leaving opacity fades in
        place so content still appears rather than snapping. The CSS keyframe
        animations are covered by the media query in index.css. */}
    <MotionConfig reducedMotion="user">
      <App />
    </MotionConfig>
  </StrictMode>,
)
