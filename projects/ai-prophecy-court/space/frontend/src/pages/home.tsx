import { useMutation, useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight, ExternalLink, Gavel, ShieldCheck, Volume2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { CourtRenderer } from "../components/court-renderer";
import { Button } from "../components/ui/button";
import { buildBattleSpec, buildEvidenceSpec } from "../court/spec";
import {
  conveneTrial,
  getBootstrap,
  recordVote,
  synthesizeVerdict,
} from "../lib/api";
import type { RoastStyle, VoteReveal } from "../lib/contracts";

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
  const sessionId = useMemo(() => crypto.randomUUID(), []);

  const trial = useMutation({
    mutationFn: () => conveneTrial(bootstrap.data!.featured_case.id, style, sessionId),
    onMutate: () => {
      setReveal(undefined);
      setChoice(undefined);
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
                  <Button disabled>Generate verdict card</Button>
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
              <div className="portrait-placeholder" aria-hidden="true">
                {item.name
                  .split(" ")
                  .map((part) => part[0])
                  .join("")}
              </div>
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
