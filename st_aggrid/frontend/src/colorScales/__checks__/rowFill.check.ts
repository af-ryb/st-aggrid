/** Runnable check for `rowFill.ts`. Run it with:
 *
 *     node st_aggrid/frontend/src/colorScales/__checks__/rowFill.check.ts
 *
 * Same arrangement as `normalize.check.ts`: Node 22 strips the types, so the
 * predicate is tested without a JS test runner. What needs a live grid is in
 * `test/test_grid_row_fill.py`.
 */
import assert from "node:assert/strict"
import { ST_ROW_FILL, readRowFillRules, rowFillFor } from "../rowFill.ts"

assert.equal(ST_ROW_FILL, "stRowFill")

// --- readRowFillRules: junk in, clean list out, never throws ---------------
for (const junk of [undefined, null, 7, "x", {}, { stRowFill: "x" }, { stRowFill: {} }]) {
  assert.deepEqual(readRowFillRules(junk), [])
}
assert.deepEqual(
  readRowFillRules({
    stRowFill: [
      { key: "a", color: "red" },
      { key: "a", color: "blue" }, // a later rule for the same key never wins
      { key: 2, color: "x" }, // a group key is always a string
      { key: "b", color: "  " }, // blank colour
      null,
      { key: "", color: "green" }, // the empty-group key is a real key
    ],
  }),
  [
    { key: "a", color: "red" },
    { key: "", color: "green" },
  ]
)

// --- rowFillFor: the group row itself, nothing else ------------------------
const rules = [
  { key: "cohort_1", color: "C" },
  { key: "1", color: "N" },
  { key: "US", color: "U" },
]
assert.equal(rowFillFor(rules, { group: true, key: "cohort_1" }), "C")
assert.equal(rowFillFor(rules, { group: true, footer: true, key: "cohort_1" }), null)
assert.equal(rowFillFor(rules, { group: false, key: "cohort_1" }), null)
assert.equal(rowFillFor(rules, { group: true, key: null }), null) // grand total
assert.equal(rowFillFor(rules, { group: true, key: "1" }), "N") // numeric column
assert.equal(rowFillFor(rules, { group: true, key: "US" }), "U")
assert.equal(rowFillFor(rules, { group: true, key: "cohort_2" }), null)
assert.equal(rowFillFor(rules, undefined), null)
assert.equal(rowFillFor([], { group: true, key: "cohort_1" }), null)
