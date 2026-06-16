import { describe, expect, it } from "vitest";

import type { CaseFile, TrialPayload, VoteReveal } from "../lib/contracts";
import { buildBattleSpec, buildEvidenceSpec } from "./spec";

const caseFile: CaseFile = {
  id: "case-1",
  person_id: "leader-1",
  title: "A prediction",
  category: "deployment",
  evidence: {
    content_id: "x:1",
    platform: "x",
    canonical_url: "https://example.com/source",
    published_at: "2026-01-01T00:00:00Z",
    exact_text: "Most tasks will run locally.",
    excerpt: "Most tasks will run locally.",
  },
  charge: "Universalizing a bounded result.",
  fair_defense: "The claim can be read directionally.",
  rationale: "The confidence outran the evidence.",
  verdict: "jury-still-out",
  review_status: "human-reviewed",
  roastability: 80,
  confidence: 90,
  court_direction: "Roast the scope.",
  featured: true,
};

describe("court specs", () => {
  it("keeps the preserved source URL in the evidence scene", () => {
    const spec = buildEvidenceSpec(caseFile);

    expect(spec.elements["evidence-quote"].props.url).toBe(
      "https://example.com/source",
    );
  });

  it("reveals model identities only after a vote", () => {
    const trial: TrialPayload = {
      case: caseFile,
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
    };
    const reveal: VoteReveal = {
      case_id: "case-1",
      choice: "a",
      model_a: "model-a",
      model_b: "model-b",
      stored: false,
      aggregate: { a: 1 },
    };

    expect(buildBattleSpec(trial).elements["roast-a"].props.model).toBeNull();
    expect(buildBattleSpec(trial, reveal, "a").elements["roast-a"].props.model).toBe(
      "model-a",
    );
  });
});
