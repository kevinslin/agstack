---
name: proofread
description: Proofread publish-ready drafts for meaningful clarity issues and broken links while preserving the author's voice.
dependencies: []
---

# Proofread

## Overview

Review a draft that is about to be published and surface meaningful issues before it goes live. Prioritize clarity and publication readiness while preserving the author's informal voice, stylistic choices, and intended emphasis.

Default to critique, not rewriting. Report issues and the smallest correction that would fix them, but do not offer a tightened, revised, or rewritten version unless the user explicitly asks for one.

When the user asks to see the fixed document, apply only the smallest corrections to material wording or grammatical-agreement issues. Preserve the author's style, word choice, structure, sentence order, spelling conventions, capitalization, punctuation, and emphasis. Do not tighten, polish, or rewrite the prose.

## Author preferences

- Treat informal spelling, loose grammar, unconventional apostrophes, missing hyphens, sentence fragments, and awkward-but-understandable phrasing as deliberate style when the meaning is clear. Do not flag examples such as "rigth," "model's," "trade offs," "end to end tests," or "Humans closing loops is still hard."
- Ignore capitalization issues, including proper-name capitalization.
- Assume the author's numbers, factual claims, comparisons, and stated demand are accurate. Do not request evidence, add `verify` labels, independently fact-check, or suggest hedging unless the user explicitly requests a factual review.
- Accept intentional hyperbole, absolutes, and rhetorical exaggeration such as "with no upper bound." Do not counter them with literal caveats or practical limitations.
- Still suggest changes that materially improve terminology or agreement, such as "code base" to "codebase" and "the best loops today are still one with the human in it" to "the best loops today are still ones with a human in them."

## Review checklist

Check the draft for:

1. Material grammatical-agreement errors or wording that obscures the intended meaning.
2. Terminology corrections that genuinely improve clarity, such as "code base" to "codebase."
3. Repeated terms or repetitive phrasing that materially distracts from the argument.
4. Clear internal contradictions or logical gaps that cannot be explained by intentional rhetoric.
5. Empty, broken, or placeholder links.

## Working style

1. Read the full draft once before marking issues.
2. Quote the exact problematic text or point to the specific claim.
3. Explain why it is a problem in one sentence.
4. Prefer the smallest correction that fixes the issue.
5. Trust the author's factual claims, numerical examples, and rhetorical choices; do not offer unsolicited accuracy suggestions.
6. Distinguish material errors from optional wording improvements, and omit stylistic nitpicks entirely.
7. Do not include a rewritten draft, tightened version, or polished alternative unless the user explicitly asks for a rewrite or fixed document.
8. For a requested fixed document, correct only material clarity and grammatical-agreement issues; preserve informal spelling, capitalization, punctuation, and other intentional style choices.

## Output format

Use these sections when reporting findings:

- `Errors`: material agreement issues, broken links, and clear internal contradictions.
- `Improvements`: useful terminology corrections, distracting repetition, or genuine logical gaps.
- `Clean`: state this explicitly when no issues are found.
- `Corrected draft`: include this only when the user asks to see the fixed document; apply only material clarity and agreement fixes while preserving the author's style.

Only provide corrected or rewritten copy when the user explicitly asks for it. Otherwise, keep the response to findings plus minimal inline fixes. When providing corrected copy, label it as minimal clarity and grammar fixes rather than a rewrite.
