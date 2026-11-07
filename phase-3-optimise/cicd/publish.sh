#!/usr/bin/env bash
# Publish the code, without docs or decision records, to the public repository as one new commit.
set -euo pipefail

PUBLIC="https://github.com/space-cowman/associator.git"
PRIVATE='(\.md$|^archive/|\.checkov\.baseline$|^phase-3-optimise/evals/redteam/|\.jsonl$|^\.github/workflows/(build|ai-gate|terraform)\.yml$)'
GITLEAKS="zricethezav/gitleaks:v8.28.0"

cd "$(git rev-parse --show-toplevel)"
test -z "$(git status --porcelain --untracked-files=no)" || { echo "Commit your changes first"; exit 1; }
sha=$(git rev-parse --short HEAD)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

git clone --quiet --depth 1 "$PUBLIC" "$work/pub" 2>/dev/null || { mkdir -p "$work/pub"; git -C "$work/pub" init --quiet -b main; git -C "$work/pub" remote add origin "$PUBLIC"; }
find "$work/pub" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
git ls-files -z | tr '\0' '\n' | grep -vE "$PRIVATE" | tar -cf - -T - | tar -xf - -C "$work/pub"
cp phase-3-optimise/cicd/public-README.md "$work/pub/README.md"

leaks=$(find "$work/pub" -name '*.md' -not -path '*/.git/*' -not -path "$work/pub/README.md" | wc -l | tr -d ' ')
test "$leaks" = 0 || { echo "Refusing: $leaks .md files in the export"; exit 1; }
docker run --rm -v "$work/pub":/scan "$GITLEAKS" dir /scan --no-banner --redact --exit-code 1 -c /scan/.gitleaks.toml >"$work/leaks.txt" 2>&1 \
  || { grep -E 'RuleID|File' "$work/leaks.txt"; echo "Refusing: gitleaks found possible secrets"; exit 1; }

cd "$work/pub"
git add -A
git diff --cached --quiet && { echo "Public repository is already up to date"; exit 0; }
git commit --quiet -m "Sync from private $sha"
git push --quiet origin main
echo "Published $sha to $PUBLIC ($(git ls-files | wc -l | tr -d ' ') files)"
