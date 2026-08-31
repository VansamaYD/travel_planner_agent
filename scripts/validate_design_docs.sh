#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
srs="$repo_root/docs/software-requirements-specification.md"
design_dir="$repo_root/docs/design"
trace_doc="$design_dir/10-requirements-traceability-and-gap-analysis.md"

failures=0

search_text() {
  if command -v rg >/dev/null 2>&1; then
    rg "$@"
  else
    grep -E "$@"
  fi
}

pass() {
  echo "PASS $1"
}

fail() {
  echo "FAIL $1"
  failures=$((failures + 1))
}

for required in README.md \
  01-system-architecture-and-adrs.md \
  02-domain-model-and-database-erd.md \
  03-state-machines-versioning-and-transactions.md \
  04-api-sse-and-file-contracts.md \
  05-agent-runtime-tools-and-provider-design.md \
  06-security-encryption-rbac-and-privacy.md \
  07-mobile-pwa-information-architecture-and-interaction.md \
  08-deployment-jobs-observability-and-operations.md \
  09-testing-evaluation-and-quality-gates.md \
  10-requirements-traceability-and-gap-analysis.md \
  11-detailed-design-review-record.md \
  12-guide-knowledge-base-and-retrieval-design.md \
  13-implementation-architecture-patterns-and-extension-contracts.md; do
  if [[ -f "$design_dir/$required" ]]; then
    pass "document exists: $required"
  else
    fail "document missing: $required"
  fi
done

requirement_ids="$(mktemp)"
trap 'rm -f "$requirement_ids"' EXIT
search_text -o '^(\*\*)?(FR|NFR)-[A-Z]+-[0-9]{3}' "$srs" | sed 's/^\*\*//' | sort > "$requirement_ids"

requirement_count="$(wc -l < "$requirement_ids" | tr -d ' ')"
unique_count="$(sort -u "$requirement_ids" | wc -l | tr -d ' ')"
fr_count="$(search_text -c '^FR-' "$requirement_ids")"
nfr_count="$(search_text -c '^NFR-' "$requirement_ids")"

if [[ "$requirement_count" = "267" && "$unique_count" = "267" ]]; then
  pass "267 unique FR/NFR definitions"
else
  fail "requirement count expected 267, got definitions=$requirement_count unique=$unique_count"
fi

if [[ "$fr_count" = "220" && "$nfr_count" = "47" ]]; then
  pass "requirement split FR=220 NFR=47"
else
  fail "requirement split expected FR=220 NFR=47, got FR=$fr_count NFR=$nfr_count"
fi

dr_count="$(search_text -o '^\*\*DR-[0-9]{3}' "$srs" | sort -u | wc -l | tr -d ' ')"
ac_count="$(search_text -o '^### AC-[0-9]{3}' "$srs" | sort -u | wc -l | tr -d ' ')"
if [[ "$dr_count" = "7" ]]; then pass "DR-001..007 present"; else fail "expected 7 DR, got $dr_count"; fi
if [[ "$ac_count" = "11" ]]; then pass "AC-001..011 present"; else fail "expected 11 AC, got $ac_count"; fi

while IFS=$'\t' read -r prefix first_id last_id; do
  last_number="${last_id##*-}"
  if search_text -q "${first_id}～${last_number}" "$trace_doc"; then
    pass "trace range present: $first_id..$last_id"
  else
    fail "trace range missing endpoint: $first_id..$last_id"
  fi
done < <(awk -F- '
  {
    prefix=$1 "-" $2
    if (!(prefix in first)) first[prefix]=$0
    last[prefix]=$0
  }
  END {
    for (prefix in first) print prefix "\t" first[prefix] "\t" last[prefix]
  }
' "$requirement_ids" | sort)

for doc in "$design_dir"/*.md; do
  fence_count="$(search_text -c '^```' "$doc" || true)"
  if (( fence_count % 2 == 0 )); then
    pass "balanced fences: $(basename "$doc")"
  else
    fail "unbalanced fences: $(basename "$doc") count=$fence_count"
  fi
done

link_failures=0
while IFS=$'\t' read -r source target; do
  clean_target="${target%%#*}"
  [[ -z "$clean_target" ]] && continue
  [[ "$clean_target" =~ ^https?:// ]] && continue
  [[ "$clean_target" =~ ^mailto: ]] && continue
  if [[ ! -e "$(dirname "$source")/$clean_target" ]]; then
    echo "FAIL broken local link: $source -> $target"
    link_failures=$((link_failures + 1))
  fi
done < <(perl -ne 'while (/\[[^]]*\]\(([^)]+)\)/g) { print "$ARGV\t$1\n" }' "$repo_root"/docs/*.md "$design_dir"/*.md)

if [[ "$link_failures" = "0" ]]; then
  pass "all local Markdown links resolve"
else
  failures=$((failures + link_failures))
fi

if search_text -q '\| (Conflict|Missing) \|' "$trace_doc"; then
  fail "trace matrix contains unresolved Conflict/Missing status"
else
  pass "no unresolved Conflict/Missing status"
fi

if search_text -q '单图 20 MB.*单 PDF 50 MB.*单次 20 文件.*家庭 20 GB' "$trace_doc" \
  && search_text -q '\| 图片.*\| 20 MB \|' "$design_dir/04-api-sse-and-file-contracts.md" \
  && search_text -q '\| PDF.*\| 50 MB \|' "$design_dir/04-api-sse-and-file-contracts.md"; then
  pass "file limit baseline aligned"
else
  fail "file limit baseline not aligned"
fi

if [[ "$failures" = "0" ]]; then
  echo "RESULT PASS"
  exit 0
fi

echo "RESULT FAIL failures=$failures"
exit 1
