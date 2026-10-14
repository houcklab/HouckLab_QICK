export const meta = {
  name: 'qicklab-apply-findings',
  description: 'Apply accepted research-review findings one at a time: implementer agent, adversarial reviewer, fix loop; the orchestrator regenerates the golden and commits each',
  phases: [{ title: 'Implement' }, { title: 'Review' }, { title: 'Fix' }],
}

const RULES = `
Repo /Users/joshua/code/research/HouckLab_QICK (branch qicklab_refactor; \`source .venv/bin/activate\`; Python 3.13,
qick 0.2.334; no hardware). The structural refactor is complete and behaviour-identical to the legacy code.
We are now applying deliberate, individually-committed improvements and bug fixes that the user approved in
principle ("make these improvements as you see fit"). Each one is ONE commit with the regression golden
regenerated and every changed golden field justified in the commit message by the orchestrator, so your job is
to make exactly the intended change, prove it, and report precisely what it changes.

RULES:
- Change only what the finding needs (plus a unit test). No drive-by cleanups, no reformatting beyond
  \`ruff format\` of the files you touched, no other behaviour changes. Keep class names, cfg key names and data
  paths unchanged. Keep docs in sync: if the finding changes documented behaviour, update the docs page that
  describes it (docs/experiments/*.md, docs/concepts/*.md, docs/architecture.md) in the same change.
- Add or extend a hardware-free test under tests/ that would have caught the bug or that pins the new
  behaviour (synthetic data; FakeSocCfg from tests/regression/capture for programs; see tests/test_program_timing.py
  and tests/test_*.py for patterns). If the change is in a tProc program, extend tests/test_program_timing.py
  with the new pinned integers and say which old pins changed and why.
- Never edit the golden, the fixtures, driver_legacy.py or tests/refactor/symbol_map.py; never set
  REGRESSION_UPDATE; never run git commands that change the index or tree.
- Verify: \`python -m compileall -q qicklab devices runners tests\`; \`ruff check --select F qicklab runners tests devices\`
  and \`ruff format <files>\`; your new/extended tests; \`python -m pytest tests/test_imports.py tests/test_program_timing.py -q\`;
  then \`python docs/dev/refactor-2026-10/tools/diff_labels.py <labels> --variants A\` (captures those run labels with the
  current code and prints every leaf that differs from the golden, classified as cfg / hw / methods / sets /
  data_digest / cfg_access ...). The labels to use are the ones the finding's golden_impact names (and any
  other label you think the change can reach); the README table in tests/regression/README.md lists all 39.
  EVERY differing leaf must be explained by the intended change; an unexpected one means you changed more
  than intended: fix it. A label the finding says is affected but which shows no diff means the change is
  not exercised there: say so.
- Report: files changed, the exact behaviour change in one paragraph a physicist can read, the test(s)
  added, the diff_labels output summary (which labels, which field classes, why each), docs updated,
  anything you could not do.
`

const IMPL_SCHEMA = {
  type: 'object',
  properties: {
    files_changed: { type: 'array', items: { type: 'string' } },
    behaviour_change: { type: 'string' },
    tests_added: { type: 'array', items: { type: 'string' } },
    golden_diff_summary: { type: 'string', description: 'per label: field classes that differ and why; or "identical"' },
    docs_updated: { type: 'array', items: { type: 'string' } },
    not_done: { type: 'array', items: { type: 'string' } },
    notes: { type: 'string' },
  },
  required: ['files_changed', 'behaviour_change', 'tests_added', 'golden_diff_summary', 'docs_updated', 'not_done', 'notes'],
}
const REVIEW_SCHEMA = {
  type: 'object',
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          file: { type: 'string' },
          severity: { type: 'string', enum: ['must-fix', 'should-fix', 'note'] },
          claim: { type: 'string' },
          evidence: { type: 'string' },
        },
        required: ['file', 'severity', 'claim', 'evidence'],
      },
    },
    verdict: { type: 'string', enum: ['approve', 'reject'] },
    summary: { type: 'string' },
  },
  required: ['findings', 'verdict', 'summary'],
}

const results = []
for (const [idx, item] of args.items.entries()) {
  const tag = `${idx + 1}/${args.items.length} ${item.id}`
  phase('Implement')
  let report = await agent(RULES + `

YOU ARE THE IMPLEMENTER. Apply this accepted finding (from the research-effectiveness review, with the
refuter's notes). Items before this one in the batch are already applied in the working tree (uncommitted or
committed): build on the current tree.

FINDING ${tag}:
${JSON.stringify(item, null, 1)}`, { label: `impl:${item.id}`.slice(0, 60), phase: 'Implement', model: 'opus', schema: IMPL_SCHEMA })

  let review = null
  for (let round = 1; round <= 2; round++) {
    phase('Review')
    review = await agent(RULES + `

YOU ARE THE ADVERSARIAL REVIEWER (round ${round}) for finding ${tag}:
${JSON.stringify(item, null, 1)}

The implementer's report:
${JSON.stringify(report, null, 1)}

Refute the claims that (a) the change is correct (the physics/engineering of the fix: units, signs, edge
cases, failure modes), (b) it is complete (every call site / every copy of the pattern), (c) nothing else
changed (read \`git diff HEAD\` of the touched files in full), (d) the tests actually pin it, (e) the golden
diff the implementer reports is exactly the diff the change must produce (run diff_labels yourself on the
labels you consider sensitive). Do not edit files. must-fix = wrong, incomplete, or an unintended change;
should-fix = weak test, missing docs, sloppy; note = observation. Verdict reject if any must-fix.`,
      { label: `review:${item.id}`.slice(0, 60), phase: 'Review', model: 'opus', schema: REVIEW_SCHEMA })
    if (!review) break
    const bad = review.findings.filter(f => f.severity !== 'note')
    log(`${tag} review ${round}: ${review.verdict}, ${bad.length} to fix`)
    if (bad.length === 0) break
    phase('Fix')
    report = await agent(RULES + `

YOU ARE THE FIX AGENT for finding ${tag}:
${JSON.stringify(item, null, 1)}

Implementer's report:
${JSON.stringify(report, null, 1)}

Reviewer findings to address (refute with evidence if one is wrong):
${JSON.stringify(bad, null, 1)}

Fix them, rerun the checks, return an updated full report of the finding's implementation.`,
      { label: `fix:${item.id}`.slice(0, 60), phase: 'Fix', model: 'opus', schema: IMPL_SCHEMA })
  }
  results.push({ id: item.id, report, review })
}
return results
