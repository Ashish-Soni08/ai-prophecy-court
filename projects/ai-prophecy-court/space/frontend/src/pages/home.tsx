import { useMutation, useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowRight,
  Check,
  Copy,
  Download,
  ExternalLink,
  Gavel,
  Image,
  ShieldCheck,
  Volume2,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { CourtRenderer } from "../components/court-renderer";
import { LeaderPortrait } from "../components/leader-portrait";
import { Button } from "../components/ui/button";
import { buildBattleSpec, buildEvidenceSpec } from "../court/spec";
import {
  conveneTrial,
  getBootstrap,
  recordVote,
  synthesizeVerdict,
} from "../lib/api";
import type { RoastStyle, VoteReveal } from "../lib/contracts";
import {
  buildVerdictCardCopy,
  createVerdictCard,
  verdictCardFilename,
} from "../lib/verdict-card";

const styleCopy: Record<RoastStyle, string> = {
  technical: "Technical",
  dark: "Dark, guarded",
  "dad-joke": "Dad joke",
};

export function HomePage() {
  const bootstrap = useQuery({ queryKey: ["bootstrap"], queryFn: getBootstrap });
  const [style, setStyle] = useState<RoastStyle>("technical");
  const [reveal, setReveal] = useState<VoteReveal>();
  const [choice, setChoice] = useState<string>();
  const [cardUrl, setCardUrl] = useState<string>();
  const [captionCopied, setCaptionCopied] = useState(false);
  const sessionId = useMemo(() => crypto.randomUUID(), []);

  const trial = useMutation({
    mutationFn: () => conveneTrial(bootstrap.data!.featured_case.id, style, sessionId),
    onMutate: () => {
      setReveal(undefined);
      setChoice(undefined);
      setCardUrl((current) => {
        if (current) URL.revokeObjectURL(current);
        return undefined;
      });
      setCaptionCopied(false);
    },
  });
  const vote = useMutation({
    mutationFn: (nextChoice: string) =>
      recordVote(bootstrap.data!.featured_case.id, style, nextChoice, sessionId),
    onSuccess: (nextReveal, nextChoice) => {
      setChoice(nextChoice);
      setReveal(nextReveal);
    },
  });
  const voice = useMutation({
    mutationFn: (winner: "a" | "b") => {
      const roast = trial.data!.roasts[winner === "a" ? 0 : 1];
      return synthesizeVerdict(
        bootstrap.data!.featured_case.id,
        style,
        winner,
        roast.text,
      );
    },
  });
  const card = useMutation({
    mutationFn: async () => {
      const input = {
        caseFile: featured,
        leader,
        trial: trial.data!,
        reveal: reveal!,
        choice: choice!,
        style,
      };
      return {
        blob: await createVerdictCard(input),
        caption: buildVerdictCardCopy(input).caption,
        filename: verdictCardFilename(input),
      };
    },
    onSuccess: ({ blob }) => {
      setCardUrl((current) => {
        if (current) URL.revokeObjectURL(current);
        return URL.createObjectURL(blob);
      });
    },
  });

  useEffect(
    () => () => {
      if (cardUrl) URL.revokeObjectURL(cardUrl);
    },
    [cardUrl],
  );

  if (bootstrap.isPending) return <CourtLoading />;
  if (bootstrap.isError || !bootstrap.data) return <CourtError />;

  const { featured_case: featured, leaders } = bootstrap.data;
  const leader = leaders.find((item) => item.id === featured.person_id)!;
  const evidenceSpec = buildEvidenceSpec(featured);
  const battleSpec = trial.data ? buildBattleSpec(trial.data, reveal, choice) : null;

  return (
    <>
      <section className="shell hero-grid">
        <div className="hero-copy">
          <div className="eyebrow">Chapter Two / The court is in session</div>
          <h1>Where confident AI predictions meet two equally confident comedians.</h1>
          <p>
            Choose the roast profile. Two small models get the same preserved evidence.
            You decide who survives cross-examination.
          </p>
          <div className="integrity-note">
            <ShieldCheck aria-hidden="true" size={18} />
            The court roasts public claims, not private lives.
          </div>
        </div>
        <aside className="case-badge">
          <div className="eyebrow">Featured filing</div>
          <div className="case-number">001</div>
          <strong>{leader.name}</strong>
          <span>{leader.company}</span>
          <span>{featured.review_status.replace("-", " ")}</span>
        </aside>
      </section>

      <section className="shell featured-trial">
        <CourtRenderer spec={evidenceSpec} />

        <div className="trial-controls">
          <div>
            <div className="scene-label">Choose the court division</div>
            <div className="style-picker">
              {bootstrap.data.roast_styles.map((item) => (
                <Button
                  key={item}
                  variant={style === item ? "primary" : "secondary"}
                  size="sm"
                  onClick={() => setStyle(item)}
                  disabled={trial.isPending}
                >
                  {styleCopy[item]}
                </Button>
              ))}
            </div>
          </div>
          <Button
            variant="dark"
            size="lg"
            onClick={() => trial.mutate()}
            disabled={trial.isPending}
          >
            <Gavel aria-hidden="true" size={19} />
            {trial.isPending ? "The models are drafting..." : "Convene Court"}
          </Button>
        </div>

        <AnimatePresence mode="wait">
          {trial.isPending && (
            <motion.div
              className="deliberation"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
            >
              <span>Evidence admitted</span>
              <span>Prompts matched</span>
              <span>Identities sealed</span>
            </motion.div>
          )}
          {battleSpec && (
            <motion.div
              key={`${style}-${Boolean(reveal)}`}
              initial={{ opacity: 0, y: 18 }}
              animate={{ opacity: 1, y: 0 }}
              className="battle-stage"
            >
              <CourtRenderer spec={battleSpec} />
              {!reveal ? (
                <div className="jury-box">
                  <div>
                    <div className="scene-label">You are the jury</div>
                    <h3>Which roast gets entered into precedent?</h3>
                  </div>
                  <div className="vote-actions">
                    <Button onClick={() => vote.mutate("a")} disabled={vote.isPending}>
                      A wins
                    </Button>
                    <Button onClick={() => vote.mutate("b")} disabled={vote.isPending}>
                      B wins
                    </Button>
                    <Button onClick={() => vote.mutate("both")} disabled={vote.isPending}>
                      Both guilty
                    </Button>
                    <Button
                      variant="ghost"
                      onClick={() => vote.mutate("dismissed")}
                      disabled={vote.isPending}
                    >
                      Case dismissed
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="verdict-actions">
                  <div>
                    <div className="scene-label">Model identities unsealed</div>
                    <p>
                      Your reaction is anonymous and{" "}
                      {reveal.stored ? "stored as an aggregate vote." : "kept in this session."}
                    </p>
                  </div>
                  {choice === "a" || choice === "b" ? (
                    <Button onClick={() => voice.mutate(choice)} disabled={voice.isPending}>
                      <Volume2 aria-hidden="true" size={17} />
                      {voice.isPending ? "Calling the clerk..." : "Hear the winning roast"}
                    </Button>
                  ) : null}
                  <Button onClick={() => card.mutate()} disabled={card.isPending}>
                    <Image aria-hidden="true" size={17} />
                    {card.isPending ? "Developing evidence..." : "Generate verdict card"}
                  </Button>
                  {voice.data?.audio_url ? (
                    <audio controls autoPlay src={voice.data.audio_url}>
                      Your browser does not support audio playback.
                    </audio>
                  ) : null}
                  {voice.data && !voice.data.audio_url ? (
                    <p className="runtime-note">{voice.data.message}</p>
                  ) : null}
                </div>
              )}
              {cardUrl && card.data ? (
                <motion.section
                  className="verdict-card-panel"
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  aria-labelledby="verdict-card-heading"
                >
                  <div>
                    <div className="scene-label">Social evidence prepared</div>
                    <h3 id="verdict-card-heading">Your verdict card is ready.</h3>
                    <p>
                      The PNG includes the public source ID, jury outcome, and unsealed
                      model credit.
                    </p>
                    <div className="verdict-card-actions">
                      <a
                        className="download-link"
                        href={cardUrl}
                        download={card.data.filename}
                      >
                        <Download aria-hidden="true" size={17} />
                        Download PNG
                      </a>
                      <Button
                        variant="secondary"
                        onClick={async () => {
                          await navigator.clipboard.writeText(card.data.caption);
                          setCaptionCopied(true);
                        }}
                      >
                        {captionCopied ? (
                          <Check aria-hidden="true" size={17} />
                        ) : (
                          <Copy aria-hidden="true" size={17} />
                        )}
                        {captionCopied ? "Caption copied" : "Copy social caption"}
                      </Button>
                    </div>
                  </div>
                  <img
                    src={cardUrl}
                    alt={`Verdict card for ${leader.name}: ${card.data.filename}`}
                  />
                </motion.section>
              ) : null}
            </motion.div>
          )}
        </AnimatePresence>
      </section>

      <section className="shell defendants">
        <div className="section-heading">
          <div>
            <div className="eyebrow">Seven public records</div>
            <h2>Choose your defendant</h2>
          </div>
          <p>Every dossier starts with preserved posts and visible platform coverage.</p>
        </div>
        <div className="leader-grid">
          {leaders.map((item, index) => (
            <Link className="leader-card" to={`/people/${item.id}`} key={item.id}>
              <LeaderPortrait leader={item} decorative />
              <div className="leader-index">{String(index + 1).padStart(2, "0")}</div>
              <h3>{item.name}</h3>
              <p>{item.company}</p>
              <span>
                Open dossier <ArrowRight aria-hidden="true" size={15} />
              </span>
            </Link>
          ))}
        </div>
      </section>

      <section className="shell source-note">
        <ExternalLink aria-hidden="true" size={18} />
        <p>
          Every quoted statement links to its collected source. Verdicts evaluate rhetoric
          inside the dataset; they are not external fact checks.
        </p>
      </section>
    </>
  );
}

function CourtLoading() {
  return (
    <section className="shell state-page">
      <div className="eyebrow">Opening the docket</div>
      <h1>The clerk is arranging the evidence.</h1>
    </section>
  );
}

function CourtError() {
  return (
    <section className="shell state-page">
      <div className="eyebrow">Court recess</div>
      <h1>The docket could not be opened.</h1>
      <p>The preserved dataset is safe; this interface needs the backend to reconvene.</p>
    </section>
  );
}
