import { describe, expect, it, vi } from "vitest";

import type { VerdictCardInput } from "./verdict-card";
import {
  buildVerdictCardCopy,
  drawWrappedText,
  verdictCardFilename,
} from "./verdict-card";

const input = {
  caseFile: {
    id: "case-1",
    person_id: "leader",
    title: "Prediction",
    category: "models",
    evidence: {
      content_id: "x:1",
      platform: "x",
      canonical_url: "https://example.com/source",
      published_at: "2026-01-01T00:00:00Z",
      exact_text: "Most tasks will run locally.",
      excerpt: "Most tasks will run locally.",
    },
    charge: "Scope inflation.",
    fair_defense: "Directionally useful.",
    rationale: "The claim needs a workload definition.",
    verdict: "jury-still-out",
    review_status: "human-reviewed",
    roastability: 90,
    confidence: 80,
    court_direction: "scope",
    featured: true,
  },
  leader: {
    id: "test-leader",
    name: "Test Leader",
    company: "Example AI",
    portrait_url: null,
    character_brief: "A test profile.",
    presence: [],
    case_ids: ["case-1"],
  },
  trial: {
    case: {} as never,
    style: "technical",
    session_id: "session",
    judge_intro: "Court is in session.",
    roasts: [
      { slot: "A", text: "Roast A", model_id: "model-a", cached: true },
      { slot: "B", text: "Roast B", model_id: "model-b", cached: true },
    ],
    model_identities_hidden: true,
    live: false,
    fallback_reason: null,
  },
  reveal: {
    case_id: "case-1",
    choice: "a",
    model_a: "model-a",
    model_b: "model-b",
    stored: false,
    aggregate: { a: 1 },
  },
  choice: "a",
  style: "technical",
} satisfies VerdictCardInput;

describe("verdict card copy", () => {
  it("uses the selected roast and revealed model", () => {
    const copy = buildVerdictCardCopy(input);

    expect(copy.verdict).toContain("ROAST A");
    expect(copy.roast).toBe("Roast A");
    expect(copy.model).toBe("model-a");
    expect(copy.caption).toContain("https://example.com/source");
  });

  it("creates a stable social image filename", () => {
    expect(verdictCardFilename(input)).toBe(
      "ai-prophecy-court-test-leader-a.png",
    );
  });

  it("ellipsizes wrapped text at the line limit", () => {
    const fillText = vi.fn();
    const context = {
      fillText,
      measureText: (text: string) => ({ width: text.length * 10 }) as TextMetrics,
    };

    drawWrappedText(context, "one two three four five six", 0, 10, 90, 20, 2);

    expect(fillText).toHaveBeenCalledTimes(2);
    expect(fillText.mock.calls[1][0]).toMatch(/…$/);
  });
});
