// Single source of truth for confidence-tier labels and what each tier
// means for trust — shared by FilterBar's chips and MatchList's badges so
// the legend can't drift between the two places it's shown.
export const TIERS = [
  { value: 'exact', label: 'Exact', hint: 'reference_id, amount, and date all matched exactly — a rule, not a guess' },
  { value: 'fuzzy-date', label: 'Fuzzy date', hint: 'reference_id and amount matched exactly; date drifted within tolerance' },
  { value: 'fuzzy-amount', label: 'Fuzzy amount', hint: 'reference_id and date matched exactly; amount drifted within tolerance' },
  { value: 'fuzzy-date-amount', label: 'Fuzzy date+amount', hint: 'reference_id matched exactly; both date and amount drifted within tolerance' },
  { value: 'llm-reasoned', label: 'LLM-reasoned', hint: "matched by Ollama's reasoning over both records — not a deterministic rule; read the reasoning before trusting it the same as an exact match" },
  { value: 'human-resolved', label: 'Human-resolved', hint: 'manually confirmed by a person, with a note explaining why' },
]

export const TIER_LABELS = Object.fromEntries(TIERS.map((t) => [t.value, t.label]))
export const TIER_HINTS = Object.fromEntries(TIERS.map((t) => [t.value, t.hint]))
