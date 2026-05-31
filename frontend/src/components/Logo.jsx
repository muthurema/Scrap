/**
 * Turnstile360 brand mark. Square inline logo. Pass `size` (px) and optional `className`.
 */
export function Logo({ size = 28, className = "" }) {
  return (
    <img
      src="/turnstile360-logo.png"
      alt="Turnstile360"
      width={size}
      height={size}
      className={`object-contain shrink-0 ${className}`}
      draggable="false"
    />
  );
}
