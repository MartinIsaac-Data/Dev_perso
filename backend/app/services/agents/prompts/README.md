# Agent prompts

One `.md` file per agent. Never inlined in Python — see ADR-009.

Three reasons this directory exists:

1. **Reviewability.** A prompt change shows up in a diff as a prompt change,
   not buried inside a Python string.
2. **Reproducibility.** `agent_run.prompt_sha256` records the hash of the file
   actually used for each call. A score from 2027 stays interpretable, and a
   prompt edited since will not match its hash — so it cannot silently pass
   for the one that produced the result.
3. **Iteration.** Improving a prompt is the work. Making that require a code
   change discourages it.

## Files (Phase 3)

| File | Agent | Role |
| --- | --- | --- |
| `posting_extraction.md` | Gap Radar | Extract required skills, tools and seniority from a raw job posting; normalise to the taxonomy; leave unmappable requirements unmapped rather than forcing them. |
| `review_board.md` | Business Case Lab | Play a sceptical CFO, COO and CIO. Attack assumptions, demand sources, hunt phantom gains and forgotten costs, score against the stored rubric. |
| `periodic_review.md` | Weekly / quarterly review | Report what moved, what stalled, which skills are decaying, where the market gap is widening. Direct and factual. No congratulation. |

## Rules these prompts follow

- **Agents critique, extract and structure. They never author.** No prompt here
  asks a model to write a business case, an article or a solution design. A
  portfolio an agent wrote is not a portfolio.
- Output is structured (JSON matching a Pydantic schema), never prose to be
  parsed by regex.
- The review board reads its rubric from `review_criterion` rather than
  carrying a copy, so the interface and the agent always score the same way.
- An unmappable input is reported as unmappable. A requirement the taxonomy
  cannot express is the most interesting signal the Gap Radar produces, and
  forcing it into the nearest existing skill destroys exactly that.
