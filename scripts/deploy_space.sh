#!/usr/bin/env bash
# T33: deploy one exact git revision to the Hugging Face Space and smoke-test it.
#
#   scripts/deploy_space.sh                 # deploy origin/main
#   scripts/deploy_space.sh <sha-or-tag>    # deploy that revision (this is also the rollback)
#   scripts/deploy_space.sh <ref> --tag     # also create and push tag deploy-<UTC time>
#
# Needs: git, hf (logged in with write access to the Space), curl, python.
# The index bundle in the bucket is not touched, so a deploy restores the index in seconds
# instead of rebuilding it. Exit code 0 only when /healthz reports the new revision, /readyz is
# 200 and one real search returns results.
set -euo pipefail

SPACE="${BERNMATCH_SPACE:-kaktamsdengami/bern-match}"
URL="${BERNMATCH_SPACE_URL:-https://kaktamsdengami-bern-match.hf.space}"
REF="${1:-origin/main}"
TAG=0; [ "${2:-}" = "--tag" ] && TAG=1

cd "$(git rev-parse --show-toplevel)"
git fetch -q origin
SHA=$(git rev-parse --verify "$REF^{commit}")
SHORT=$(git rev-parse --short "$SHA")
echo "deploying $REF = $SHORT to $SPACE"

STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
git archive "$SHA" app config/suppression.json requirements.lock deploy/hf-space/entrypoint.sh | tar -x -C "$STAGE"
git show "$SHA:deploy/hf-space/Dockerfile" > "$STAGE/Dockerfile"
git show "$SHA:deploy/hf-space/README.md" > "$STAGE/README.md"
echo "$SHA" > "$STAGE/app/REVISION"

hf upload "$SPACE" "$STAGE" . --repo-type space --delete "app/**" --delete "deploy/**" \
  --commit-message "Deploy $SHORT ($REF)"

echo "waiting for the Space to serve $SHORT (image build + start, usually 2-4 min)"
for i in $(seq 1 90); do
  rev=$(curl -s -m 10 "$URL/healthz" | python -c "import sys,json
try: print(json.load(sys.stdin).get('revision') or '')
except Exception: print('')" 2>/dev/null || true)
  [ "$rev" = "$SHA" ] && break
  sleep 10
done
[ "$rev" = "$SHA" ] || { echo "FAILED: /healthz never reported $SHORT (last: ${rev:-none})"; exit 1; }
echo "ok: /healthz reports $SHORT"

for i in $(seq 1 60); do
  code=$(curl -s -m 10 -o /dev/null -w '%{http_code}' "$URL/readyz" || true)
  [ "$code" = 200 ] && break
  sleep 5
done
[ "$code" = 200 ] || { echo "FAILED: /readyz is $code (bundle restore or build problem; see the Space logs)"; exit 1; }
echo "ok: /readyz 200"

n=$(curl -s -m 60 -X POST "$URL/api/v1/search" -H 'Content-Type: application/json' \
  -d '{"schema_version":"1","query":"continuous glucose monitoring","revision":1,"entity_type":null,"company_context":null,"needs":[],"enrichment_requested":false}' \
  | python -c "import sys,json; print(len(json.load(sys.stdin)['results']))")
[ "$n" -ge 1 ] || { echo "FAILED: smoke search returned no results"; exit 1; }
echo "ok: smoke search returned $n results"

if [ "$TAG" = 1 ]; then
  T="deploy-$(date -u +%Y%m%d-%H%M)"
  git tag "$T" "$SHA" && git push -q origin "$T" && echo "tagged $T"
fi
echo "DEPLOYED $SHA at $(date -u +%FT%TZ)"
