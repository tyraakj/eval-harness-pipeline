# Feature status and delivery plan

Glyph is being consolidated around a versioned evaluation specification. This
document distinguishes implemented behavior from product goals so a README claim
is never mistaken for a tested capability.

## Implemented and usable now

| Capability | Entry point | Evidence |
|---|---|---|
| Versioned deterministic suite | `glyph run --spec path.yaml` | JSONL trial artifact |
| Weighted, required rubric | `rubric.criteria` in the spec | `rubric.<id>` grades and evidence |
| Target integration | `target.factory` in the spec | target version and trajectory |
| Exact/content/tool/trajectory/retrieval checks | `graders` in the spec | per-grader grade |
| Artifact comparison and release policy | `glyph compare`, `glyph release` | comparison/release output |
| Optional model and human evaluation APIs | Python APIs | cost/review artifacts |

## Policy migration status

New evaluations use the evaluation spec plus its `specialized_policy` YAML. The
shipped `src/glyph/specialized_workers/default_policy.yaml` is only a
compatibility profile. Score maps, release profiles, and task construction now
use that external policy. Legacy dataclass defaults remain for direct Python
callers until their callers and tests migrate to policy fixtures.

## Deliberately no longer inferred

The old `glyph run --workers` category table reported a score even when no
criterion had been declared. It is deprecated. The presence of a tool call or a
retrieval event does not demonstrate good tool use or good retrieval. Define a
check, rubric criterion, or a model/human rubric instead.

## Work required before calling a capability production-ready

These README-level ambitions need integration and acceptance tests before they
can be advertised as default behavior:

- Container or VM-backed network/process isolation (the supplied network policy
  records intent; it does not OS-enforce egress).
- A first-class spec compiler for every specialized security, graph, output, and
  performance worker. Their current Python policy objects still contain legacy
  defaults and should be migrated criterion by criterion.
- A CLI workflow for human-review assignment/adjudication and model-judge
  configuration; APIs exist, but the spec/CLI UX is not yet unified.
- End-to-end web-console and background-worker acceptance tests.

The acceptance rule for each item is: a versioned spec can configure it, the
artifact preserves its inputs/version/evidence, and a test proves both passing
and failing behavior without hard-coded success prose.
