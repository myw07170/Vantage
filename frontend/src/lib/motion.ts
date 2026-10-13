/* Shared entrance animations: staggered fade-and-rise. */

export const stagger = {
  animate: { transition: { staggerChildren: 0.06 } },
}

export const fadeUp = {
  initial: { opacity: 0, y: 12 },
  animate: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.4, ease: [0.4, 0, 0.2, 1] as const },
  },
}
