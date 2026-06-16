import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ExternalLink, FileText, Radio } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { LeaderPortrait } from "../components/leader-portrait";
import { getLeader } from "../lib/api";

export function DossierPage() {
  const { personId = "" } = useParams();
  const dossier = useQuery({
    queryKey: ["leader", personId],
    queryFn: () => getLeader(personId),
  });

  if (dossier.isPending) {
    return <section className="shell state-page"><h1>Opening dossier...</h1></section>;
  }
  if (dossier.isError || !dossier.data) {
    return <section className="shell state-page"><h1>Dossier not found.</h1></section>;
  }

  const { leader, cases } = dossier.data;
  return (
    <section className="shell dossier-page">
      <Link className="back-link" to="/">
        <ArrowLeft aria-hidden="true" size={16} /> Return to live floor
      </Link>
      <div className="dossier-hero">
        <LeaderPortrait leader={leader} variant="hero" />
        <div>
          <div className="eyebrow">Individual dossier / AI character brief</div>
          <h1>{leader.name}</h1>
          <h2>{leader.company}</h2>
          <p>{leader.character_brief}</p>
        </div>
      </div>

      <div className="dossier-grid">
        <div>
          <div className="section-heading compact">
            <div>
              <div className="eyebrow">Curated case files</div>
              <h2>Claims on the docket</h2>
            </div>
          </div>
          {cases.length ? (
            cases.map((caseFile) => (
              <article className="case-file" key={caseFile.id}>
                <FileText aria-hidden="true" size={20} />
                <div>
                  <div className="scene-label">
                    {caseFile.category} / roastability {caseFile.roastability}
                  </div>
                  <h3>{caseFile.title}</h3>
                  <p>{caseFile.evidence.excerpt}</p>
                  <a href={caseFile.evidence.canonical_url} target="_blank" rel="noreferrer">
                    Preserved source <ExternalLink aria-hidden="true" size={14} />
                  </a>
                </div>
              </article>
            ))
          ) : (
            <div className="empty-docket">
              <p>The extraction record exists, but no claim has passed the docket screen yet.</p>
            </div>
          )}
        </div>

        <aside className="presence-ledger">
          <div className="eyebrow">Platform presence</div>
          {leader.presence.map((presence) => (
            <article key={presence.platform}>
              <Radio aria-hidden="true" size={17} />
              <div>
                <strong>{presence.platform}</strong>
                <span>{presence.status.replaceAll("-", " ")}</span>
                {presence.url && (
                  <a href={presence.url} target="_blank" rel="noreferrer">
                    Verified profile
                  </a>
                )}
                {presence.absence_quip && <p>{presence.absence_quip}</p>}
              </div>
            </article>
          ))}
        </aside>
      </div>
    </section>
  );
}
