# Demo Recording Script

Use this for the required hackathon demo video.

## Command

```powershell
cd projects/ai-prophecy-court/space/frontend
npm run record:demo
```

The script starts the Gradio app, opens Chrome with Playwright, records the
main product path, writes the video, and shuts the app server down again:

```text
projects/ai-prophecy-court/space/frontend/demo-output/ai-prophecy-court-demo.webm
```

## What The Recording Shows

1. Open AI Prophecy Court on the featured public claim.
2. Choose the dad-joke division.
3. Convene the two-model roast battle.
4. Show that model identities are sealed before voting.
5. Vote for Roast A.
6. Reveal the competing model identities.
7. Generate the downloadable verdict card.
8. Open Clement Delangue's dossier.
9. Open the archive.

## Voiceover

```text
AI Prophecy Court puts public AI predictions on trial.

The evidence is source-linked, and the app roasts the claim rather than the
person. I choose a roast style, then two sub-32B models receive the same
evidence packet. Their identities stay sealed until the jury votes.

After the vote, the app reveals which model wrote each roast, prepares a
source-stamped verdict card, and lets me download a social-ready artifact.

The Gradio Space works with reviewed curated fallbacks, and the optional Modal
runtime can swap in live Nemotron and MiniCPM model calls when credentials are
configured.
```

Keep the final video under two minutes. After upload, add the video URL to the
Space README and the submission form.
