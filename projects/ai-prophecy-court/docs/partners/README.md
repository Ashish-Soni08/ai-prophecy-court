# Partner Technology Decisions

This is the living decision log for partner technology considered by AI
Prophecy Court. Decisions may change after model and deployment evaluations.

| Partner | Status | V1 role | Reason |
| --- | --- | --- | --- |
| OpenBMB | Adopted | MiniCPM4.1-8B, MiniCPM5-1B, and VoxCPM2 | Claim processing, one Roast Battle competitor, safety/direction, and theatrical voice |
| NVIDIA | Adopted | Nemotron 3 Nano 4B | Strictly sub-32B Roast Battle competitor without the parameter ambiguity of the larger checkpoint |
| Black Forest Labs | Adopted | FLUX.2 Klein 4B, offline only | Reviewed leader portraits and featured verdict-card artwork |
| Modal | Adopted | Batch processing, model serving, media jobs, feedback store | Keeps GPU work outside the lightweight Gradio Space and provides one operational boundary |
| Cohere Labs | Deferred | Possible multilingual verdicts | Useful extension, but not required for the English V1 court loop |
| JetBrains | Deferred | Possible prediction-debugging exhibit | Mellum is eligible but does not solve a core V1 product problem |

## Guardrails

- Every selected model must be strictly below 32B parameters.
- Generated media cannot contain factual quotes, dates, citations, or verdict
  text.
- The app must remain useful when every partner runtime is unavailable.
- Partner technology is adopted for product value, not badge accumulation.
