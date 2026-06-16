import type {
  CaseFile,
  Leader,
  RoastStyle,
  TrialPayload,
  VoteReveal,
} from "./contracts";

const CARD_WIDTH = 1200;
const CARD_HEIGHT = 1500;
const INK = "#24221d";
const PAPER = "#efe7d1";
const PAPER_LIGHT = "#fffaf0";
const ACID = "#a8db49";
const GOLD = "#ad8b45";
const MUTED = "#706a5e";

export type VerdictCardInput = {
  caseFile: CaseFile;
  leader: Leader;
  trial: TrialPayload;
  reveal: VoteReveal;
  choice: string;
  style: RoastStyle;
};

export type VerdictCardCopy = {
  verdict: string;
  roast: string;
  model: string;
  caption: string;
};

export function buildVerdictCardCopy(input: VerdictCardInput): VerdictCardCopy {
  const style = input.style.replace("-", " ");
  if (input.choice === "a" || input.choice === "b") {
    const index = input.choice === "a" ? 0 : 1;
    const slot = input.choice.toUpperCase();
    const model = input.choice === "a" ? input.reveal.model_a : input.reveal.model_b;
    return {
      verdict: `ROAST ${slot} ENTERS PRECEDENT`,
      roast: input.trial.roasts[index].text,
      model,
      caption: [
        `${input.leader.name}'s public AI prediction entered AI Prophecy Court.`,
        `The ${style} division ruled for Roast ${slot}, written by ${model}.`,
        `Source: ${input.caseFile.evidence.canonical_url}`,
        "#BuildSmall #AIProphecyCourt",
      ].join("\n\n"),
    };
  }

  if (input.choice === "both") {
    return {
      verdict: "BOTH ADVOCATES FOUND FUNNY",
      roast: "The jury entered both roasts into precedent. A rare unanimous conviction.",
      model: `${input.reveal.model_a} + ${input.reveal.model_b}`,
      caption: [
        `${input.leader.name}'s public AI prediction entered AI Prophecy Court.`,
        `The ${style} division found both small models guilty of landing the joke.`,
        `Source: ${input.caseFile.evidence.canonical_url}`,
        "#BuildSmall #AIProphecyCourt",
      ].join("\n\n"),
    };
  }

  return {
    verdict: "CASE DISMISSED",
    roast: "The prediction escaped on a technicality. The court reserves the right to reconvene when reality files new evidence.",
    model: "The jury",
    caption: [
      `${input.leader.name}'s public AI prediction survived AI Prophecy Court.`,
      `The ${style} division dismissed the case, for now.`,
      `Source: ${input.caseFile.evidence.canonical_url}`,
      "#BuildSmall #AIProphecyCourt",
    ].join("\n\n"),
  };
}

export function verdictCardFilename(input: VerdictCardInput): string {
  return `ai-prophecy-court-${input.leader.id}-${input.choice}.png`;
}

export async function createVerdictCard(input: VerdictCardInput): Promise<Blob> {
  const canvas = document.createElement("canvas");
  canvas.width = CARD_WIDTH;
  canvas.height = CARD_HEIGHT;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("This browser cannot render the verdict card.");

  const copy = buildVerdictCardCopy(input);
  drawBackground(context);

  context.fillStyle = INK;
  context.font = "800 25px ui-monospace, monospace";
  context.letterSpacing = "3px";
  context.fillText("AI PROPHECY COURT / PUBLIC RECORD", 92, 112);
  context.letterSpacing = "0px";

  context.strokeStyle = INK;
  context.lineWidth = 3;
  context.strokeRect(72, 60, CARD_WIDTH - 144, CARD_HEIGHT - 120);

  context.fillStyle = GOLD;
  context.font = "500 190px Georgia, serif";
  context.fillText("§", 88, 330);

  context.fillStyle = INK;
  context.font = "500 76px Georgia, serif";
  drawWrappedText(context, input.leader.name, 300, 220, 790, 82, 2);
  context.fillStyle = MUTED;
  context.font = "700 28px ui-monospace, monospace";
  context.fillText(input.leader.company.toUpperCase(), 305, 380);

  context.fillStyle = ACID;
  context.fillRect(72, 455, CARD_WIDTH - 144, 100);
  context.fillStyle = INK;
  context.font = "900 27px ui-monospace, monospace";
  context.fillText(copy.verdict, 104, 518);

  context.fillStyle = MUTED;
  context.font = "800 20px ui-monospace, monospace";
  context.fillText("THE ADMITTED CLAIM", 96, 635);
  context.fillStyle = INK;
  context.font = "500 42px Georgia, serif";
  const claimBottom = drawWrappedText(
    context,
    `“${input.caseFile.evidence.excerpt}”`,
    96,
    700,
    1008,
    52,
    5,
  );

  context.strokeStyle = GOLD;
  context.lineWidth = 3;
  context.beginPath();
  context.moveTo(96, claimBottom + 30);
  context.lineTo(1104, claimBottom + 30);
  context.stroke();

  context.fillStyle = MUTED;
  context.font = "800 20px ui-monospace, monospace";
  context.fillText("THE JURY'S SELECTION", 96, claimBottom + 90);
  context.fillStyle = INK;
  context.font = "500 46px Georgia, serif";
  const roastBottom = drawWrappedText(
    context,
    copy.roast,
    96,
    claimBottom + 155,
    1008,
    56,
    5,
  );

  context.fillStyle = PAPER_LIGHT;
  context.fillRect(72, 1262, CARD_WIDTH - 144, 118);
  context.fillStyle = INK;
  context.font = "800 18px ui-monospace, monospace";
  context.fillText("IDENTITY UNSEALED", 96, 1302);
  context.font = "700 22px ui-monospace, monospace";
  drawWrappedText(context, copy.model, 96, 1340, 980, 28, 2);

  context.fillStyle = MUTED;
  context.font = "700 17px ui-monospace, monospace";
  context.fillText(
    `${input.caseFile.evidence.content_id} / ${input.style.toUpperCase()} DIVISION`,
    96,
    Math.min(roastBottom + 52, 1230),
  );

  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => (blob ? resolve(blob) : reject(new Error("Card export failed."))),
      "image/png",
      0.94,
    );
  });
}

function drawBackground(context: CanvasRenderingContext2D) {
  context.fillStyle = PAPER;
  context.fillRect(0, 0, CARD_WIDTH, CARD_HEIGHT);
  context.strokeStyle = "rgba(36,34,29,.055)";
  context.lineWidth = 2;
  for (let x = -CARD_HEIGHT; x < CARD_WIDTH; x += 46) {
    context.beginPath();
    context.moveTo(x, 0);
    context.lineTo(x + CARD_HEIGHT, CARD_HEIGHT);
    context.stroke();
  }
}

export function drawWrappedText(
  context: Pick<CanvasRenderingContext2D, "fillText" | "measureText">,
  text: string,
  x: number,
  y: number,
  maxWidth: number,
  lineHeight: number,
  maxLines: number,
): number {
  const words = text.replace(/\s+/g, " ").trim().split(" ");
  const lines: string[] = [];
  let current = "";

  for (const word of words) {
    const candidate = current ? `${current} ${word}` : word;
    if (context.measureText(candidate).width <= maxWidth || !current) {
      current = candidate;
      continue;
    }
    lines.push(current);
    current = word;
    if (lines.length === maxLines - 1) break;
  }
  if (current && lines.length < maxLines) lines.push(current);

  const consumedWords = lines.join(" ").split(" ").length;
  if (consumedWords < words.length && lines.length) {
    let last = lines.length - 1;
    while (
      context.measureText(`${lines[last]}…`).width > maxWidth &&
      lines[last].includes(" ")
    ) {
      lines[last] = lines[last].slice(0, lines[last].lastIndexOf(" "));
    }
    lines[last] = `${lines[last]}…`;
  }

  lines.forEach((line, index) => context.fillText(line, x, y + index * lineHeight));
  return y + Math.max(lines.length - 1, 0) * lineHeight;
}
