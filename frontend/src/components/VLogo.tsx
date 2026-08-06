/**
 * The Vantage mark.
 *
 * A component rather than a bare `<img>` at each site so the asset path lives
 * in one place, and so the accessibility call is made deliberately: the mark
 * repeats the wordmark next to it in most of the shell, and a logo announced
 * twice is worse than one announced not at all. `alt` therefore defaults to
 * decorative, and callers that show it *alone* — the collapsed rail, a bare
 * header — pass a label in.
 */
export function VLogo({
  size = 36,
  alt = '',
  className = '',
}: {
  size?: number
  /** Leave empty where a visible "Vantage" already names the app. */
  alt?: string
  className?: string
}) {
  return (
    <img
      src="/brand/vantage-logo.png"
      alt={alt}
      width={size}
      height={size}
      draggable={false}
      decoding="async"
      className={`shrink-0 select-none ${className}`}
      style={{ width: size, height: size }}
    />
  )
}
