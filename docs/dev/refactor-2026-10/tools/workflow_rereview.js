export const meta = {
  name: 'qicklab-rereview',
  description: 'Re-review the final state of an applied finding (adversarial reviewer, fix loop) when the last fix round was left unreviewed',
  phases: [{ title: 'Review' }, { title: 'Fix' }],
}
const RULES = `
Repo /Users/joshua/code/research/HouckLab_QICK (branch qicklab_refactor; \`source .venv/bin/activate\`; no hardware).
Individually-committed bug fixes are being applied; the orchestrator regenerates the regression golden per commit.
Never edit the golden, fixtures, driver_legacy.py, symbol_map.py; never set REGRESSION_UPDATE; never run git commands
that change the index or tree. Checks: compileall, \`ruff check --select F qicklab runners tests devices\`, the item's
tests, \`python docs/dev/refactor-2026-10/tools/diff_labels.py <labels> --variants A\` (captures run labels and classifies
every leaf that differs from the golden). Other agents are concurrently editing other files (active_reset, runs/*,
core/experiment.py, analysis/hmm.py, analysis/readout.py, analysis/spectroscopy.py, analysis/fitting.py,
experiments/single_shot.py, experiments/qubit_spec.py, experiments/rabi.py): their diffs on shared labels are not
yours; only the files of this item may be edited by the fix agent.
`
const REVIEW_SCHEMA = { type: 'object', properties: { findings: { type: 'array', items: { type: 'object', properties: { file: { type: 'string' }, severity: { type: 'string', enum: ['must-fix', 'should-fix', 'note'] }, claim: { type: 'string' }, evidence: { type: 'string' } }, required: ['file', 'severity', 'claim', 'evidence'] } }, verdict: { type: 'string', enum: ['approve', 'reject'] }, summary: { type: 'string' } }, required: ['findings', 'verdict', 'summary'] }
const FIX_SCHEMA = { type: 'object', properties: { files_changed: { type: 'array', items: { type: 'string' } }, what_changed: { type: 'string' }, golden_diff_summary: { type: 'string' }, notes: { type: 'string' } }, required: ['files_changed', 'what_changed', 'golden_diff_summary', 'notes'] }
let review = null, fix = null
for (let round = 1; round <= 2; round++) {
  phase('Review')
  review = await agent(RULES + `
YOU ARE THE ADVERSARIAL REVIEWER (re-review round ${round}) of finding ${args.id} in its CURRENT working-tree state.
Item: ${args.item}
Files of this item: ${args.files}
Context: ${args.context}
${fix ? 'Fix agent report from the previous round: ' + JSON.stringify(fix, null, 1) : ''}
Refute that (a) the change is correct (physics/engineering, units, signs, edge cases, failure modes), (b) complete,
(c) nothing else changed in these files (\`git diff HEAD -- <files>\` in full), (d) the tests pin it (run them),
(e) the golden diff is exactly what the change must produce (run diff_labels on the sensitive labels). Do not edit
files. must-fix = wrong/incomplete/unintended change; should-fix = weak test, missing docs; note = observation.`,
    { label: `rereview:${args.id}:${round}`, phase: 'Review', model: 'opus', schema: REVIEW_SCHEMA })
  if (!review) break
  const bad = review.findings.filter(f => f.severity !== 'note')
  log(`re-review ${round}: ${review.verdict}, ${bad.length} to fix`)
  if (bad.length === 0) break
  phase('Fix')
  fix = await agent(RULES + `
YOU ARE THE FIX AGENT for finding ${args.id}. Item: ${args.item}
Files you may edit: ${args.files}
Reviewer findings to address (refute with evidence if wrong):
${JSON.stringify(bad, null, 1)}
Fix them, rerun the checks and the item's tests, run diff_labels on the sensitive labels, and report.`,
    { label: `refix:${args.id}:${round}`, phase: 'Fix', model: 'opus', schema: FIX_SCHEMA })
}
return { id: args.id, review, fix }