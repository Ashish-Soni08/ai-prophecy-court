import type { CSSProperties } from "react";

import type { Leader } from "../lib/contracts";
import { cn } from "../lib/utils";

const palettes = [
  { wash: "#f4d06f", accent: "#a8db49", ink: "#24221d" },
  { wash: "#f2a65a", accent: "#536b36", ink: "#24221d" },
  { wash: "#9cc5a1", accent: "#ad8b45", ink: "#24221d" },
  { wash: "#d6b4fc", accent: "#a8db49", ink: "#24221d" },
  { wash: "#f28c8c", accent: "#536b36", ink: "#24221d" },
  { wash: "#8ecae6", accent: "#ad8b45", ink: "#24221d" },
  { wash: "#cdb4db", accent: "#536b36", ink: "#24221d" },
];

type LeaderPortraitProps = {
  leader: Leader;
  variant?: "card" | "hero";
  decorative?: boolean;
};

export function leaderInitials(name: string) {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");
}

function paletteFor(id: string) {
  const hash = Array.from(id).reduce(
    (total, character) => total + character.charCodeAt(0),
    0,
  );
  return palettes[hash % palettes.length];
}

export function LeaderPortrait({
  leader,
  variant = "card",
  decorative = false,
}: LeaderPortraitProps) {
  const palette = paletteFor(leader.id);
  const style = {
    "--portrait-wash": palette.wash,
    "--portrait-accent": palette.accent,
    "--portrait-ink": palette.ink,
  } as CSSProperties;

  if (leader.portrait_url) {
    return (
      <img
        className={cn("court-portrait", `court-portrait-${variant}`)}
        src={leader.portrait_url}
        alt={decorative ? "" : `${leader.name} reviewed portrait`}
        aria-hidden={decorative ? "true" : undefined}
      />
    );
  }

  return (
    <div
      className={cn("court-portrait", `court-portrait-${variant}`)}
      style={style}
      aria-label={decorative ? undefined : `Illustrated docket sigil for ${leader.name}`}
      aria-hidden={decorative ? "true" : undefined}
    >
      <svg viewBox="0 0 240 300" focusable="false" aria-hidden="true">
        <rect className="court-portrait-wash" width="240" height="300" rx="0" />
        <path
          className="court-portrait-rays"
          d="M-20 252 120 22l140 230M10 292 120 44l110 248M44 318 120 64l76 254"
        />
        <circle className="court-portrait-orbit" cx="120" cy="122" r="70" />
        <path
          className="court-portrait-bust"
          d="M76 242c8-36 29-58 44-58s36 22 44 58H76Zm15-95c0-27 13-48 29-48s29 21 29 48-13 48-29 48-29-21-29-48Z"
        />
        <path className="court-portrait-gavel" d="m67 76 16-16 45 45-16 16-45-45Zm75 69 13-13 40 40-13 13-40-40Z" />
      </svg>
      <span className="court-portrait-initials">{leaderInitials(leader.name)}</span>
      <span className="court-portrait-label">{leader.company}</span>
    </div>
  );
}
