import { Archive, Scale } from "lucide-react";
import type { PropsWithChildren } from "react";
import { Link, NavLink } from "react-router-dom";

export function SiteShell({ children }: PropsWithChildren) {
  return (
    <>
      <header className="masthead">
        <div className="shell masthead-inner">
          <Link className="brand" to="/">
            <span className="brand-seal">
              <Scale aria-hidden="true" size={22} />
            </span>
            <span>
              <strong>AI Prophecy Court</strong>
              <small>Small models. Large claims. Cited jokes.</small>
            </span>
          </Link>
          <nav aria-label="Court sections">
            <NavLink to="/">Live floor</NavLink>
            <NavLink to="/archive">
              <Archive aria-hidden="true" size={15} /> Archive
            </NavLink>
          </nav>
        </div>
      </header>
      <main>{children}</main>
      <footer className="shell footer">
        <span>Built with Codex / Gradio Server / small open models</span>
        <span>AI interpretation, source-linked evidence, no synthetic quotes</span>
      </footer>
    </>
  );
}
