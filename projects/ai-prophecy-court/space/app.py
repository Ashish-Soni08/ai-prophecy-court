"""Deployable Gradio shell for AI Prophecy Court."""

from __future__ import annotations

import gradio as gr

LEADERS = [
    ("Sam Altman", "OpenAI", "X"),
    ("Dario Amodei", "Anthropic", "X"),
    ("Sundar Pichai", "Google", "X + LinkedIn"),
    ("Satya Nadella", "Microsoft", "X + LinkedIn"),
    ("Clement Delangue", "Hugging Face", "X + LinkedIn"),
    ("Jensen Huang", "NVIDIA", "LinkedIn"),
    ("Elon Musk", "xAI", "X"),
]


def leader_cards() -> str:
    cards = "".join(
        f"""
        <article class="leader-card">
          <span class="source">{source}</span>
          <h3>{name}</h3>
          <p>{company}</p>
          <div class="status"><i></i> Evidence indexed</div>
        </article>
        """
        for name, company, source in LEADERS
    )
    return f'<section class="leader-grid">{cards}</section>'


CSS = """
:root {
  --ink: #26231d;
  --paper: #f3ead0;
  --paper-light: #fffaf0;
  --acid: #a8db49;
  --gold: #ad8b45;
  --muted: #6f695c;
}
.gradio-container {
  max-width: none !important;
  color: var(--ink) !important;
  background:
    radial-gradient(circle at 10% 0%, rgb(173 139 69 / 12%), transparent 32rem),
    repeating-linear-gradient(92deg, transparent 0 42px, rgb(38 35 29 / 2%) 43px),
    var(--paper) !important;
}
.main { max-width: 1480px; margin: 0 auto; padding: 24px 28px 64px; }
.hero {
  border: 2px solid var(--ink);
  background: var(--paper-light);
  padding: clamp(28px, 5vw, 72px);
  box-shadow: 10px 10px 0 var(--ink);
}
.eyebrow, .source, .status {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  text-transform: uppercase;
  letter-spacing: .12em;
  font-size: 11px;
}
.hero h1 {
  margin: 12px 0 14px;
  max-width: 900px;
  font-family: Georgia, serif;
  font-size: clamp(52px, 9vw, 126px);
  line-height: .82;
  letter-spacing: -.065em;
}
.hero-copy { max-width: 720px; color: var(--muted); font-size: 18px; }
.badge {
  display: inline-block;
  margin-top: 24px;
  padding: 8px 12px;
  border: 1px solid var(--ink);
  background: var(--acid);
  font-weight: 700;
}
.section-title {
  margin: 54px 0 18px;
  padding-bottom: 12px;
  border-bottom: 2px solid var(--ink);
  font-family: Georgia, serif;
  font-size: 34px;
}
.leader-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
  gap: 14px;
}
.leader-card {
  min-height: 180px;
  padding: 20px;
  border: 1px solid var(--ink);
  background: rgb(255 250 240 / 72%);
}
.leader-card h3 { margin: 34px 0 2px; font-family: Georgia, serif; font-size: 25px; }
.leader-card p { margin: 0; color: var(--muted); }
.source { float: right; padding: 5px 7px; border: 1px solid var(--gold); }
.status { margin-top: 24px; }
.status i {
  display: inline-block;
  width: 8px;
  height: 8px;
  margin-right: 7px;
  border-radius: 50%;
  background: var(--acid);
  box-shadow: 0 0 0 2px var(--ink);
}
.notice {
  margin-top: 18px;
  padding: 16px 18px;
  border-left: 6px solid var(--gold);
  background: rgb(255 250 240 / 70%);
}
footer { margin-top: 40px; color: var(--muted); font-size: 13px; }
"""


with gr.Blocks(title="AI Prophecy Court") as demo:
    with gr.Column(elem_classes="main"):
        gr.HTML(
            """
            <header class="hero">
              <div class="eyebrow">Chapter Two · An Adventure in Thousand Token Wood</div>
              <h1>AI Prophecy Court</h1>
              <p class="hero-copy">
                Public predictions enter as evidence. An AI judge checks the
                record, finds the gap between confidence and reality, and
                delivers a cited roast.
              </p>
              <span class="badge">COURT IN PREPARATION</span>
            </header>
            <h2 class="section-title">The defendants</h2>
            """
        )
        gr.HTML(leader_cards())
        gr.HTML(
            """
            <aside class="notice">
              <strong>Current build:</strong> deployable interface shell with
              the verified X and LinkedIn roster. Retrieval, evidence matching,
              and AI-generated verdicts arrive in the next backend milestone.
            </aside>
            <footer>
              Built with Codex · Source-linked evidence · No synthetic quotes
            </footer>
            """
        )


if __name__ == "__main__":
    demo.launch(css=CSS)
