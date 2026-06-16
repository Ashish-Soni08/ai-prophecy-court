import { z } from "zod";

export const roastStyleSchema = z.enum(["technical", "dark", "dad-joke"]);
export type RoastStyle = z.infer<typeof roastStyleSchema>;

export const presenceSchema = z.object({
  platform: z.string(),
  status: z.string(),
  url: z.string().nullable(),
  absence_quip: z.string().nullable(),
});

export const leaderSchema = z.object({
  id: z.string(),
  name: z.string(),
  company: z.string(),
  portrait_url: z.string().nullable(),
  character_brief: z.string(),
  presence: z.array(presenceSchema),
  case_ids: z.array(z.string()),
});
export type Leader = z.infer<typeof leaderSchema>;

export const caseSchema = z.object({
  id: z.string(),
  person_id: z.string(),
  title: z.string(),
  category: z.string(),
  evidence: z.object({
    content_id: z.string(),
    platform: z.string(),
    canonical_url: z.string(),
    published_at: z.string(),
    exact_text: z.string(),
    excerpt: z.string(),
  }),
  charge: z.string(),
  fair_defense: z.string(),
  rationale: z.string(),
  verdict: z.enum(["guilty", "not-guilty", "jury-still-out"]),
  review_status: z.enum(["human-reviewed", "ai-screened"]),
  roastability: z.number(),
  confidence: z.number(),
  court_direction: z.string(),
  featured: z.boolean(),
});
export type CaseFile = z.infer<typeof caseSchema>;

export const bootstrapSchema = z.object({
  featured_case: caseSchema,
  leaders: z.array(leaderSchema),
  archive: z.array(caseSchema),
  roast_styles: z.array(roastStyleSchema),
  model_battle: z.array(z.string()),
});
export type BootstrapPayload = z.infer<typeof bootstrapSchema>;

export const trialSchema = z.object({
  case: caseSchema,
  style: roastStyleSchema,
  session_id: z.string(),
  judge_intro: z.string(),
  roasts: z.array(
    z.object({
      slot: z.string(),
      text: z.string(),
      model_id: z.string(),
      cached: z.boolean(),
    }),
  ),
  model_identities_hidden: z.boolean(),
  live: z.boolean(),
  fallback_reason: z.string().nullable(),
});
export type TrialPayload = z.infer<typeof trialSchema>;

export const voteRevealSchema = z.object({
  case_id: z.string(),
  choice: z.string(),
  model_a: z.string(),
  model_b: z.string(),
  stored: z.boolean(),
  aggregate: z.record(z.string(), z.number()),
});
export type VoteReveal = z.infer<typeof voteRevealSchema>;

export const voiceAssetSchema = z.object({
  case_id: z.string(),
  style: roastStyleSchema,
  winner: z.string(),
  status: z.string(),
  audio_url: z.string().nullable(),
  message: z.string(),
});
export type VoiceAsset = z.infer<typeof voiceAssetSchema>;

export const leaderDetailSchema = z.object({
  leader: leaderSchema,
  cases: z.array(caseSchema),
});
export type LeaderDetail = z.infer<typeof leaderDetailSchema>;
