import type { CaseFile, TrialPayload, VoteReveal } from "../lib/contracts";

export type CourtSpec = {
  root: string;
  elements: Record<
    string,
    {
      type: "Proceeding" | "EvidenceQuote" | "Finding" | "RoastCard";
      props: Record<string, unknown>;
      children: string[];
    }
  >;
};

export function buildEvidenceSpec(caseFile: CaseFile): CourtSpec {
  return {
    root: "evidence-scene",
    elements: {
      "evidence-scene": {
        type: "Proceeding",
        props: {
          label: "Exhibit A / source locked",
          title: "The claim enters the record",
          tone: "evidence",
        },
        children: ["evidence-quote", "charge", "defense", "verdict"],
      },
      "evidence-quote": {
        type: "EvidenceQuote",
        props: {
          quote: caseFile.evidence.excerpt,
          speaker: caseFile.person_id,
          company: caseFile.category,
          platform: caseFile.evidence.platform,
          date: new Date(caseFile.evidence.published_at).toLocaleDateString(),
          url: caseFile.evidence.canonical_url,
        },
        children: [],
      },
      charge: {
        type: "Finding",
        props: { heading: "The charge", body: caseFile.charge, kind: "charge" },
        children: [],
      },
      defense: {
        type: "Finding",
        props: {
          heading: "The fairest defense",
          body: caseFile.fair_defense,
          kind: "defense",
        },
        children: [],
      },
      verdict: {
        type: "Finding",
        props: {
          heading: caseFile.verdict.replaceAll("-", " "),
          body: caseFile.rationale,
          kind: "verdict",
        },
        children: [],
      },
    },
  };
}

export function buildBattleSpec(
  trial: TrialPayload,
  reveal?: VoteReveal,
  selection?: string,
): CourtSpec {
  return {
    root: "battle-scene",
    elements: {
      "battle-scene": {
        type: "Proceeding",
        props: {
          label: `${trial.style.replace("-", " ")} division / anonymous bench`,
          title: "Two small models approach the punchline",
          tone: "battle",
        },
        children: ["roast-a", "roast-b"],
      },
      "roast-a": {
        type: "RoastCard",
        props: {
          slot: "A",
          text: trial.roasts[0].text,
          model: reveal?.model_a ?? null,
          revealed: Boolean(reveal),
          selected: selection === "a" || selection === "both",
        },
        children: [],
      },
      "roast-b": {
        type: "RoastCard",
        props: {
          slot: "B",
          text: trial.roasts[1].text,
          model: reveal?.model_b ?? null,
          revealed: Boolean(reveal),
          selected: selection === "b" || selection === "both",
        },
        children: [],
      },
    },
  };
}
