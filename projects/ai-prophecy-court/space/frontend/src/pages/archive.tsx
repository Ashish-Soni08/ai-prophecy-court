import { useQuery } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";

import { getBootstrap } from "../lib/api";

export function ArchivePage() {
  const bootstrap = useQuery({ queryKey: ["bootstrap"], queryFn: getBootstrap });

  return (
    <section className="shell archive-page">
      <div className="eyebrow">Reviewed precedent only</div>
      <h1>Verdict Archive</h1>
      <p className="archive-intro">
        Live experiments do not publish themselves. Only source-checked, reviewed cases
        enter this room.
      </p>
      <div className="archive-list">
        {bootstrap.data?.archive.map((caseFile) => (
          <article key={caseFile.id}>
            <div className="archive-number">CASE 001</div>
            <div>
              <div className="scene-label">
                {caseFile.review_status.replace("-", " ")} / {caseFile.verdict.replaceAll("-", " ")}
              </div>
              <h2>{caseFile.title}</h2>
              <p>{caseFile.rationale}</p>
            </div>
            <a href={caseFile.evidence.canonical_url} target="_blank" rel="noreferrer">
              Source <ExternalLink aria-hidden="true" size={14} />
            </a>
          </article>
        ))}
      </div>
    </section>
  );
}
