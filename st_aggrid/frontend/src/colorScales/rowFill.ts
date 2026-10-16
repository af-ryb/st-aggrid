/**
 * Group-row fill: a grid-level list of `{ key, color }` rules in
 * `context.stRowFill`, each painting the group row whose own key equals `key`.
 *
 * Pure, imports nothing (see `__checks__/rowFill.check.ts`). The predicate is
 * the consumer's old `getRowStyle` blob minus subtotal footers: AG-Grid gives a
 * footer node `group: true` and its group's `key`, so `footer` is the only
 * thing that tells the two apart. The grand total's key is `null` and a leaf
 * is not a group, so neither can match.
 *
 * Python (`st_aggrid/row_fill.py`) rejects a bad rule loudly; this copy only
 * guards grid options that never went through it, and drops what it cannot
 * use.
 */

export const ST_ROW_FILL = "stRowFill"

export type RowFillRule = { key: string; color: string }

type RowFillNode = { group?: boolean; footer?: boolean; key?: string | null }

/** The usable rules in a grid `context`; the first rule for a key wins. */
export function readRowFillRules(context: unknown): RowFillRule[] {
  if (typeof context !== "object" || context === null) return []
  const raw = (context as Record<string, unknown>)[ST_ROW_FILL]
  if (!Array.isArray(raw)) return []

  const rules: RowFillRule[] = []
  const seen = new Set<string>()
  for (const entry of raw) {
    if (typeof entry !== "object" || entry === null) continue
    const { key, color } = entry as Record<string, unknown>
    if (typeof key !== "string" || seen.has(key)) continue
    if (typeof color !== "string" || color.trim() === "") continue
    seen.add(key)
    rules.push({ key, color })
  }
  return rules
}

/** The colour for this row, or `null` when no rule covers it. */
export function rowFillFor(
  rules: RowFillRule[],
  node: RowFillNode | null | undefined
): string | null {
  if (!node || node.group !== true || node.footer === true) return null
  const key = node.key
  if (typeof key !== "string") return null
  return rules.find((rule) => rule.key === key)?.color ?? null
}
