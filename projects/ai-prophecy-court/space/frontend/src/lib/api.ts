import { Client } from "@gradio/client";

import {
  bootstrapSchema,
  leaderDetailSchema,
  trialSchema,
  voteRevealSchema,
  voiceAssetSchema,
  type BootstrapPayload,
  type LeaderDetail,
  type RoastStyle,
  type TrialPayload,
  type VoteReveal,
  type VoiceAsset,
} from "./contracts";

let gradioClient: Promise<Client> | undefined;

function backendOrigin() {
  return import.meta.env.VITE_GRADIO_ORIGIN || window.location.origin;
}

async function client() {
  gradioClient ??= Client.connect(backendOrigin());
  return gradioClient;
}

export async function getBootstrap(): Promise<BootstrapPayload> {
  const response = await fetch(`${backendOrigin()}/api/bootstrap`);
  if (!response.ok) throw new Error("The court docket could not be opened.");
  return bootstrapSchema.parse(await response.json());
}

export async function getLeader(personId: string): Promise<LeaderDetail> {
  const response = await fetch(`${backendOrigin()}/api/leaders/${personId}`);
  if (!response.ok) throw new Error("This dossier could not be found.");
  return leaderDetailSchema.parse(await response.json());
}

function firstString(data: unknown): string {
  if (Array.isArray(data) && typeof data[0] === "string") return data[0];
  if (typeof data === "string") return data;
  throw new Error("The court returned an unexpected response.");
}

export async function conveneTrial(
  caseId: string,
  style: RoastStyle,
  sessionId: string,
): Promise<TrialPayload> {
  const connected = await client();
  const result = await connected.predict("/convene_trial", {
    case_id: caseId,
    style,
    session_id: sessionId,
  });
  return trialSchema.parse(JSON.parse(firstString(result.data)));
}

export async function recordVote(
  caseId: string,
  style: RoastStyle,
  choice: string,
  sessionId: string,
): Promise<VoteReveal> {
  const connected = await client();
  const result = await connected.predict("/record_vote", {
    case_id: caseId,
    style,
    choice,
    session_id: sessionId,
  });
  return voteRevealSchema.parse(JSON.parse(firstString(result.data)));
}

export async function synthesizeVerdict(
  caseId: string,
  style: RoastStyle,
  winner: string,
  text: string,
): Promise<VoiceAsset> {
  const connected = await client();
  const result = await connected.predict("/synthesize_verdict", {
    case_id: caseId,
    style,
    winner,
    text,
  });
  return voiceAssetSchema.parse(JSON.parse(firstString(result.data)));
}
