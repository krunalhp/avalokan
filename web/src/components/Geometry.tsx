import type { Zone } from "../api";

/** SVG drawing of the normalized vertical line and rectangular zone (0–1 frame coordinates). */
function Shapes({ lineX, zone }: { lineX?: number; zone?: Zone }) {
  const valid = (v: number) => Number.isFinite(v) && v >= 0 && v <= 1;
  const z = zone && zone.every(valid) && zone[2] > zone[0] && zone[3] > zone[1] ? zone : null;
  return (
    <>
      {z && (
        <rect
          class="geo-zone"
          x={z[0] * 100}
          y={z[1] * 100}
          width={(z[2] - z[0]) * 100}
          height={(z[3] - z[1]) * 100}
          vector-effect="non-scaling-stroke"
        />
      )}
      {lineX !== undefined && valid(lineX) && (
        <line class="geo-line" x1={lineX * 100} x2={lineX * 100} y1={0} y2={100} vector-effect="non-scaling-stroke" />
      )}
    </>
  );
}

export function GeometryPreview({ lineX, zone }: { lineX: number; zone: Zone }) {
  return (
    <svg class="geo-preview" viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="Geometry preview">
      <Shapes lineX={lineX} zone={zone} />
    </svg>
  );
}

export function GeometryOverlay({ lineX, zone }: { lineX?: number; zone?: Zone }) {
  return (
    <svg class="geo-overlay" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
      <Shapes lineX={lineX} zone={zone} />
    </svg>
  );
}
