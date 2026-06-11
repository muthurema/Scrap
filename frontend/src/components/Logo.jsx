/**
 * CIDSA brand mark — a GIS globe glyph in a square tile.
 * Pass `size` (px) for the tile dimensions and optional `className`.
 */
import { GlobeHemisphereWest } from "@phosphor-icons/react";

export function Logo({ size = 28, className = "" }) {
  return (
    <span
      className={`inline-flex items-center justify-center shrink-0 bg-emerald-600 text-white rounded-sm ${className}`}
      style={{ width: size, height: size }}
      aria-label="CIDSA"
    >
      <GlobeHemisphereWest size={Math.round(size * 0.62)} weight="bold" />
    </span>
  );
}
