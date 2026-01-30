KC_PROMPT = """You are an expert research concept extractor.

Given a paper's title and (optionally) abstract, extract two sets of Key Concepts (KC):

1) proposed_concepts:
- Concepts/ideas/methods explicitly introduced, proposed, or newly defined by the paper.
- This includes new models, algorithms, objectives, datasets/benchmarks (only if introduced), training schemes, or novel problem formulations.
- Be conservative: only include what is clearly supported by the title/abstract.

2) prerequisite_concepts:
- Concepts that a reader should know to understand the paper.
- These are background notions implied by the title/abstract, but should still be clearly relevant.

Return ONLY valid, raw JSON. No extra text. No markdown.

### Output schema (must follow exactly)
{
  "proposed_concepts": ["..."],
  "prerequisite_concepts": ["..."]
}

### Rules
- Each field MUST be a list of UNIQUE strings.
- Each concept should be a short noun phrase (2–6 words preferred).
- Avoid overly generic terms like "AI", "deep learning", "neural network" unless the input is truly that generic.
- Do NOT hallucinate details not present in the title/abstract.
- If the abstract is missing or empty:
  - Use ONLY the title evidence.
  - Prefer fewer items (0–6) and be extra conservative.
- Provide 0–12 items per list. If none, use [].

### Input
Title: "{INPUT_TITLE}"
Abstract: "{INPUT_ABSTRACT}"

Output: """


ALIAS_PROMPT = """You are an expert entity normalizer.

Your task is to generate alias surface forms for a given canonical concept name.
These aliases are used to map different user-written strings to the SAME concept node
in a concept graph.

Return ONLY valid, raw JSON. No extra text. No markdown.

### Rules:
- "alias" MUST be a list of UNIQUE strings (no duplicates).
- Do NOT include the canonical name itself.
- Do NOT include trivial variants that are the same as the canonical name
  (case-only changes, extra spaces, or punctuation-only changes).
- If you cannot find at least 1 safe alias, output: {"alias": []}
- Provide 1 to 6 aliases max.

### What counts as an alias
Generate only realistic surface-form variants that people actually write:
- Case variants (upper/lower/mixed)
- Spacing variants (with or without spaces)
- Punctuation variants (hyphens, dots, slashes)
- Acronyms OR full names ONLY if they are unambiguous and commonly used
- Very common typos or misspellings (max 2–3)

Do NOT be creative. Be conservative.

### Task
Canonical name: "{INPUT_name}"
Output: """


EDGE_ABOUT_PROMPT = """You are an expert scientific paper analyst.

Given a PAPER (title + abstract) and a CONCEPT, score whether the paper INTRODUCES/PROPOSES/DEFINES the concept as a main contribution.

Return ONLY valid, raw JSON. No extra text. No markdown.

The output JSON must have exactly these fields:
{
  "strength": number (float between 0 and 1),
  "reason": string (1–2 short sentences, generic, no names, no dates)
}

strength guidelines:
- 0.9–1.0: explicitly introduced/proposed/defined as a key contribution
- 0.6–0.8: strongly central but not explicitly claimed as new
- 0.3–0.5: mentioned as part of method, not a main contribution
- 0.0–0.2: not introduced by the paper

Rules:
- Use ONLY the provided title/abstract; do not assume extra details.
- Be conservative: if unclear, lower the score.

PAPER_TITLE: "{PAPER_TITLE}"
PAPER_ABSTRACT: "{PAPER_ABSTRACT}"
CONCEPT: "{CONCEPT}"

Output:
"""

EDGE_IN_PROMPT = """You are an expert curriculum designer.

Given a PAPER (title + abstract) and a CONCEPT, score how necessary the concept is as prerequisite knowledge to understand the paper.

Return ONLY valid, raw JSON. No extra text. No markdown.

The output JSON must have exactly these fields:
{
  "strength": number (float between 0 and 1),
  "reason": string (1–2 short sentences, generic, no names, no dates)
}

strength guidelines:
- 0.9–1.0: required prerequisite; paper relies heavily on it
- 0.6–0.8: very helpful background
- 0.3–0.5: weak/optional background
- 0.0–0.2: not really a prerequisite

Rules:
- Use ONLY the provided title/abstract; do not assume extra details.
- Be conservative: if unclear, lower the score.

PAPER_TITLE: "{PAPER_TITLE}"
PAPER_ABSTRACT: "{PAPER_ABSTRACT}"
CONCEPT: "{CONCEPT}"

Output:
"""

EDGE_REF_BY_PROMPT = """You are an expert scientific paper analyst.

Given a TARGET paper (the one we want to understand) and a REFERENCED paper,
score how essential the referenced paper is for understanding the target paper.

Return ONLY valid, raw JSON. No extra text. No markdown.
Output schema:
{"strength": number}

strength guidelines (0~1):
- 0.9–1.0: essential; heavily relied upon
- 0.6–0.8: very helpful; key background/method
- 0.3–0.5: somewhat relevant; minor support
- 0.0–0.2: weak/optional

Use ONLY the provided text. Be conservative if unclear.

TARGET_TITLE: "{TARGET_TITLE}"
TARGET_ABSTRACT: "{TARGET_ABSTRACT}"

REF_TITLE: "{REF_TITLE}"
REF_ABSTRACT: "{REF_ABSTRACT}"

CITATION_INTENTS: {INTENTS}
IS_INFLUENTIAL: {IS_INF}
CONTEXTS: {CONTEXTS}

Output: """

DESC_PROMPT = """You are an expert scientific editor.

Write a SINGLE-SENTENCE, one-line description of the paper based ONLY on the title, abstract, and categories.
Be precise and conservative. Do NOT add facts not supported by the input.

Return ONLY valid, raw JSON. No extra text. No markdown.

### Output schema (must follow exactly)
{
  "description": "..."
}

### Rules
- "description" MUST be one sentence in Korean.
- 18–30 words (prefer concise, information-dense).
- Mention the paper's main contribution or purpose (method + task/problem + key idea).
- You MAY use categories only as a high-level field hint (e.g., NLP, CV, medicine) but do NOT infer specific methods/results from them.
- Avoid hype and vague phrases (e.g., "novel", "state-of-the-art") unless explicitly stated.
- If abstract is missing/empty: rely only on the title + categories; be extra conservative and keep it very short (8–16 words).
- Do not include citations, author names, or URLs.

### Input
Title: "{INPUT_TITLE}"
Abstract: "{INPUT_ABSTRACT}"
Categories: "{INPUT_CATEGORIES}"

Output: """
