export const meta = {
  name: 'qicklab-3b-area',
  description: 'Phase 3b for one area: cleanup agent, adversarial old-vs-new reviewer, fix loop (area passed as args)',
  phases: [{ title: 'Cleanup' }, { title: 'Review' }, { title: 'Fix' }],
}

const A = args
const RULES = `
Repo: /Users/joshua/code/research/HouckLab_QICK, branch qicklab_refactor. Activate the venv first:
\`source .venv/bin/activate\`. Phases 3a-i..3a-iii are committed: the repo IS the qicklab package now
(qicklab/, devices/, runners/CSTQ03_BFC.py, tests/, docs/). Phase 3b = per-area cleanup with behaviour
preserved. The acceptance test of every commit is the hardware-free regression golden
(tests/regression, README there): same experiment classes, same cfg dicts (every key), same compiled
tProc programs, same method calls / display attributes / saved payloads, same yoko command sequence, same
cfg keys read and written per experiment class. It must stay BYTE-IDENTICAL in this commit (no
regeneration, no allowlist use). Bug fixes are separate later commits: a known wrong behaviour stays wrong
here, even when it is one line (design.md "Known bugs").

Read first: docs/dev/refactor-2026-10/design.md (Invariants, Migration map row notes, Comment policy, Package
layering), the symbol map rows of kind deleted/merged for your files (tests/refactor/symbol_map.py; a
'deleted' row cites the audit, a 'merged' row carries a proof), and the audit sections named below.

AREA: ${A.area}
FILES (yours to edit): ${A.files.join(', ')}
ALLOWED CHANGES (the whole list, nothing beyond it):
${A.allowed_changes}
FORBIDDEN: ${A.forbidden}
DOCS PAGES for lab notes: ${A.docs_pages}
AUDIT: ${A.audit_sections}

IMPROVEMENTS (functionality-preserving; the user asked for them, 2026-10-13). Besides the allowed list you
may make the code meaningfully better where the result is provably identical: (a) robustness with identical
outcomes (import the submodule you actually use instead of relying on another package's import side effect,
e.g. scipy.optimize; \`with\` blocks for files that are opened and closed on every path; \`is None\` / plain
truthiness instead of \`== None\` / \`== True\` ONLY where the operand is provably None/scalar/bool, never for
arrays); (b) performance where the arithmetic is unchanged element for element (boolean-mask indexing or
one vectorised expression instead of per-element Python loops with np.append; hoisting a loop-invariant
computation) -- never reorder a reduction (sum/mean/dot/cumsum), never change dtypes, defaults, rounding,
random streams, KMeans/fit parameters, plotting output, prints that run during a measurement, or exception
types; (c) an always-true/always-false guard replaced by what it actually does, with the same side effects.
Each improvement is listed in your report under \`improvements\` with a one-sentence proof of identity; the
golden must stay byte-identical (if a digest flips, revert that improvement). Anything that would improve
the code but change a result, a saved value or a message goes under \`improvement_candidates\` (file, what,
why it changes behaviour) for the user to approve later; do not apply it.

Never run git commands that change the index or tree (git diff/show/log are fine; use \`git diff HEAD --
<file>\` to see what you changed and \`git show HEAD:<file>\` for the pre-cleanup text). Never edit
tests/refactor/symbol_map.py, the golden, the fixtures, driver_legacy.py or capture.py. Never set
REGRESSION_UPDATE.
Checks: \`python -m compileall -q qicklab devices runners tests\`; \`ruff check --select F qicklab runners tests devices\`
(and ruff format <files> after editing, the tree is ruff-formatted); \`python -m tests.refactor.equivalence --phase 3b\`
(structural: every 3b-deleted symbol gone, merge targets present; AST failures on symbols you deliberately
changed under the allowed list are expected and must be listed in your report, nothing else may fail);
\`python -m pytest tests/test_imports.py tests/test_program_timing.py -q\`; and the fast golden subset
\`REGRESSION_LABELS=${A.regression_labels} REGRESSION_VARIANTS=A python -m pytest tests/regression -q\`
(must pass; a diff there means you changed behaviour: revert that change, never the golden). The
orchestrator runs the full suite (10 min) after the review; do not run it yourself.
`

const CLEAN_SCHEMA = {
  type: 'object',
  properties: {
    files_edited: { type: 'array', items: { type: 'string' } },
    changes: { type: 'array', items: { type: 'string' }, description: 'one line per change, with the allowed-list item it implements' },
    deleted_symbols: { type: 'array', items: { type: 'string' } },
    docs_added: { type: 'array', items: { type: 'string' } },
    improvements: { type: 'array', items: { type: 'string' }, description: 'functionality-preserving improvements applied: file, what, one-sentence proof the result is identical' },
    improvement_candidates: { type: 'array', items: { type: 'string' }, description: 'improvements NOT applied because they would change a result/message; file, what, why' },
    skipped: { type: 'array', items: { type: 'string' }, description: 'allowed items you did not do, and why' },
    checks: { type: 'string', description: 'actual outputs/summaries of the checks you ran' },
    notes: { type: 'string' },
  },
  required: ['files_edited', 'changes', 'deleted_symbols', 'docs_added', 'improvements', 'improvement_candidates', 'skipped', 'checks', 'notes'],
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
          evidence: { type: 'string', description: 'old vs new text or a concrete input that behaves differently' },
        },
        required: ['file', 'severity', 'claim', 'evidence'],
      },
    },
    verdict: { type: 'string', enum: ['approve', 'reject'] },
    summary: { type: 'string' },
  },
  required: ['findings', 'verdict', 'summary'],
}

function reviewPrompt(round, cleanupReport) {
  return RULES + `

YOU ARE THE ADVERSARIAL REVIEWER (round ${round}). A cleanup agent edited the files above. Its report:
${JSON.stringify(cleanupReport, null, 1)}

Your job is to REFUTE the claim that behaviour is preserved. Read the full old and new text of every edited
file (\`git show HEAD:<file>\` vs the working tree; \`git diff HEAD -- <file>\`), not just the diff hunks.
Look for: a deleted symbol that something still references (grep the whole tree incl. tests, runners and
docs code blocks); a deleted symbol the symbol map does not mark deleted/merged; a 'merged' or moved helper
whose arithmetic, defaults, argument order, dtype handling, rounding, logging, plotting, saved keys or
exception behaviour differ from the original; a comment deleted that was load-bearing (e.g. a noqa, a type
comment) or a lab note deleted without landing on the docs page; a changed import binding (name now bound to a
different object); changes outside the allowed list; a bug silently fixed (forbidden here); anything that
would change the regression golden (cfg keys/values, program, display attributes, saved payload keys, yoko
writes, cfg keys read/written). For every entry under \`improvements\`, check the identity proof yourself:
same values element for element (write a quick old-vs-new numpy comparison on random inputs when a loop was
vectorised: np.array_equal, not allclose), same dtype, same side effects, same exceptions; a reordered
reduction or a changed dtype is a must-fix. Run the checks yourself (compileall, ruff F, equivalence --phase 3b, the
golden subset given above; you may also run a different REGRESSION_LABELS subset you consider more
sensitive to these files). Do NOT edit any file.
Report every finding with concrete evidence and a severity: must-fix = behaviour or golden changes, or a rule
of the brief is broken; should-fix = allowed-list item done incompletely or sloppily; note = observation.
Verdict 'reject' if any must-fix exists, else 'approve'. Be specific: file, symbol, old text, new text.`
}

phase('Cleanup')
let report = await agent(RULES + `

YOU ARE THE CLEANUP AGENT. Do exactly the allowed changes, verify with the checks, and report. Prefer
leaving something undone (and saying so) over exceeding the allowed list. When you move a lab-note comment
to docs, quote the numbers/dates verbatim on the page and keep the page's existing structure. When the
symbol map marks a symbol 'merged' with a proof, the surviving function must be textually the same math as
the original; keep the proof's caveats (e.g. a different error-message text is NOT acceptable to merge
unless the note says the behaviour change is limited to that message and no test/golden sees it: in doubt,
keep both and report).`, { label: `3b:${A.area}:cleanup`, phase: 'Cleanup', model: 'opus', schema: CLEAN_SCHEMA })

let review = null
for (let round = 1; round <= 3; round++) {
  phase('Review')
  review = await agent(reviewPrompt(round, report), { label: `3b:${A.area}:review${round}`, phase: 'Review', model: 'opus', schema: REVIEW_SCHEMA })
  if (!review) break
  const mustFix = review.findings.filter(f => f.severity === 'must-fix')
  const shouldFix = review.findings.filter(f => f.severity === 'should-fix')
  log(`review ${round}: ${review.verdict}, ${mustFix.length} must-fix, ${shouldFix.length} should-fix, ${review.findings.length - mustFix.length - shouldFix.length} notes`)
  if (review.verdict === 'approve' && shouldFix.length === 0) break
  if (round === 3) break
  phase('Fix')
  report = await agent(RULES + `

YOU ARE THE FIX AGENT (after review round ${round}). The cleanup agent's report:
${JSON.stringify(report, null, 1)}

The adversarial reviewer's findings (must-fix and should-fix must be addressed; a finding you believe is
wrong must be refuted with evidence in your report, not ignored):
${JSON.stringify(review.findings.filter(f => f.severity !== 'note'), null, 1)}

Fix them within the allowed list (a must-fix about a behaviour change is fixed by restoring the original
behaviour, never by touching the golden), rerun the checks, and return an updated full report of the
area's state (all changes, not just the fixes).`, { label: `3b:${A.area}:fix${round}`, phase: 'Fix', model: 'opus', schema: CLEAN_SCHEMA })
}
return { area: A.area, report, review }