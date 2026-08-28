// Single source of truth for confidence-tier labels, what each tier means
// for trust, and its provenance group — shared by FilterBar's chips and
// MatchList's badges so neither the legend nor the color can drift between
// the places they're shown.
//
// `group` drives the provenance color palette (see index.css's
// --tier-rule/--tier-llm/--success roles): every rule-tier confidence
// (exact/fuzzy-*) shares one "rule" color — they're all "the deterministic
// engine decided this," differentiated by label, not hue — while
// llm-reasoned and human-resolved each get their own.
export const TIERS = [
  { value: 'exact', label: 'Exact', group: 'rule', hint: 'reference_id, amount, and date all matched exactly — a rule, not a guess' },
  { value: 'fuzzy-date', label: 'Fuzzy date', group: 'rule', hint: 'reference_id and amount matched exactly; date drifted within tolerance' },
  { value: 'fuzzy-amount', label: 'Fuzzy amount', group: 'rule', hint: 'reference_id and date matched exactly; amount drifted within tolerance' },
  { value: 'fuzzy-date-amount', label: 'Fuzzy date+amount', group: 'rule', hint: 'reference_id matched exactly; both date and amount drifted within tolerance' },
  { value: 'llm-reasoned', label: 'LLM-reasoned', group: 'llm', hint: "matched by Ollama's reasoning over both records — not a deterministic rule; read the reasoning before trusting it the same as an exact match" },
  { value: 'human-resolved', label: 'Human-resolved', group: 'human', hint: 'manually confirmed by a person, with a note explaining why' },
]

export const TIER_LABELS = Object.fromEntries(TIERS.map((t) => [t.value, t.label]))
export const TIER_HINTS = Object.fromEntries(TIERS.map((t) => [t.value, t.hint]))
export const TIER_GROUPS = Object.fromEntries(TIERS.map((t) => [t.value, t.group]))
