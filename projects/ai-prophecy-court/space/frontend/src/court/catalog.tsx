import { defineCatalog } from "@json-render/core";
import { defineRegistry } from "@json-render/react";
import { schema } from "@json-render/react/schema";
import { ExternalLink, Scale } from "lucide-react";
import { z } from "zod";

export const courtCatalog = defineCatalog(schema, {
  components: {
    Proceeding: {
      props: z.object({
        label: z.string(),
        title: z.string(),
        tone: z.enum(["evidence", "verdict", "battle"]),
      }),
      description: "A bounded courtroom scene containing evidence or roast candidates.",
    },
    EvidenceQuote: {
      props: z.object({
        quote: z.string(),
        speaker: z.string(),
        company: z.string(),
        platform: z.string(),
        date: z.string(),
        url: z.string(),
      }),
      description: "An exact, source-linked public statement. Props are server locked.",
    },
    Finding: {
      props: z.object({
        heading: z.string(),
        body: z.string(),
        kind: z.enum(["charge", "defense", "verdict"]),
      }),
      description: "A reviewed rhetorical finding with a fixed semantic role.",
    },
    RoastCard: {
      props: z.object({
        slot: z.enum(["A", "B"]),
        text: z.string(),
        model: z.string().nullable(),
        revealed: z.boolean(),
        selected: z.boolean(),
      }),
      description: "One anonymous model roast with an identity reveal state.",
    },
  },
  actions: {},
});

export const { registry: courtRegistry } = defineRegistry(courtCatalog, {
  components: {
    Proceeding: ({ props, children }) => (
      <section className={`proceeding proceeding-${props.tone}`}>
        <div className="scene-label">{props.label}</div>
        <h2>{props.title}</h2>
        <div className="proceeding-body">{children}</div>
      </section>
    ),
    EvidenceQuote: ({ props }) => (
      <article className="evidence-quote">
        <blockquote>{props.quote}</blockquote>
        <div className="evidence-source">
          <span>
            {props.speaker} / {props.company}
          </span>
          <span>
            {props.platform} / {props.date}
          </span>
          <a href={props.url} target="_blank" rel="noreferrer">
            Open source <ExternalLink aria-hidden="true" size={14} />
          </a>
        </div>
      </article>
    ),
    Finding: ({ props }) => (
      <article className={`finding finding-${props.kind}`}>
        <div className="finding-icon">
          <Scale aria-hidden="true" size={18} />
        </div>
        <div>
          <div className="scene-label">{props.heading}</div>
          <p>{props.body}</p>
        </div>
      </article>
    ),
    RoastCard: ({ props }) => (
      <article className={`roast-card ${props.selected ? "roast-card-selected" : ""}`}>
        <div className="roast-number">Roast {props.slot}</div>
        <p>{props.text}</p>
        <div className="model-reveal">
          {props.revealed ? props.model : "Model identity sealed"}
        </div>
      </article>
    ),
  },
});
