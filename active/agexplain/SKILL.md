---
name: agexplain
description: Deep-dive into a topic with a coordinator and scoped subagents, then deliver a concise, evidence-backed explanation with context and clear recommendations.
dependencies: []
---

# agexplain

Use for a deep explanation of a system, implementation, proposal, or decision.
Investigate deeply; present only what helps the reader understand or decide.
The current agent coordinates the work and owns the final answer.

## Frame the question

Identify the question, intended reader, desired outcome, and relevant constraints.
Use available context; ask only when ambiguity would materially change the work.
Define what evidence would make the answer sufficient and what is out of scope.
Explanation does not authorize implementation, external writes, or configuration
changes. Keep investigation read-only unless the user separately authorizes more.

## Investigate with subagents

Delegate bounded evidence questions to investigator subagents. Start with one;
add others only for independent lines of inquiry that can run alongside useful
coordinator work. Prefer appropriate specialist roles when available, without
requiring a particular agent name, model, or tool provider.
Use at most three investigators and one reviewer; reuse them for follow-ups.
Tell subagents not to delegate further unless the user explicitly requests it.

Give each investigator:

- The user's question and relevant context, including constraints and non-goals.
- A distinct question, source scope, and stopping condition; avoid duplicate work.
- A request for findings, supporting source locations, and material uncertainties.

The coordinator establishes the big picture and investigates gaps not assigned
to others. For implementations, trace the relevant inputs, owners, decisions,
state changes, and outputs. For recommendations, establish the current approach,
the problem it leaves, and the constraints that determine a better choice.

Prefer current primary evidence. Distinguish observed behavior, documented intent,
inference, and proposals. Treat agent summaries as leads: inspect the evidence
behind consequential claims and resolve contradictions before relying on them.
Do not infer consensus merely because multiple agents repeat the same source.

## Synthesize and challenge

Write one coherent explanation, not a concatenation of investigator reports.
Give a reviewer subagent the draft, the original question, constraints, and source
references. Ask it to check:

- Does the answer address the actual question, with support for its key claims?
- Can the reader understand the problem and mechanism without prior agent context?
- Are recommendations tied to a concrete benefit, cost, and relevant alternative?
- What can be removed without losing meaning or a decision-relevant caveat?

The reviewer returns specific corrections, not another full investigation or a
list of hypothetical edge cases. The coordinator verifies and fixes material
issues. Reuse agents for focused follow-ups only when a gap could change the
answer. Stop when the question is answered or remaining uncertainty is explicit;
do not iterate for stylistic unanimity. If subagents are unavailable, disclose
that limitation and perform the same investigation and critique locally.

## Deliver

Lead with the answer. Include only the following elements that the question needs:

- **Context:** what exists today, who needs it, and what problem or constraint matters.
- **Explanation:** how it works and why, using concrete actors and actions.
- **Recommendation:** what to do, why it fits this situation, and the main tradeoff.
- **Evidence and gaps:** source links beside key claims and any uncertainty that
  could change the conclusion. Never present a proposal as implemented or verified.

Keep essential context even when shortening. Define unfamiliar terms at first use;
use an example, table, or diagram only when it makes the relationship clearer.
Avoid generic introductions, repeated conclusions, unsupported superlatives,
jargon without explanation, exhaustive option lists, and narration of agent work.
Do not force the elements above into separate headings for a short answer.

Return the explanation in the conversation unless the user requests an artifact.
The coordinator's final check: every paragraph must help the reader understand,
decide, or act; every recommendation must explain why it makes sense here.
