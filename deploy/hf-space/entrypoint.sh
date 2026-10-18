#!/bin/sh
# Space start-up: serve the app at once, and build the search index in the background the
# first time, from files placed in the persistent bucket (mounted at /data).
#
#   /data/corpus.jsonl            T06 export (python -m app.ingest export)
#   /data/knowledge/              optional T08 output (entities.jsonl + claims.jsonl, same corpus)
#   /data/models/e5-small/        fetched by this script (pinned, hash-checked)
#   /data/indexes/<generation>/   written by the build; /data/READY marks the live generation
#
# A restart finds READY and skips the build. Delete /data/READY to force a rebuild.
# Logs: /data/build.log, failure marker: /data/build.failed (contains the exit code).
set -u
DATA="${BERNMATCH_DATA_DIR:-/data}"
export BERNMATCH_DATA_DIR="$DATA"
export BERNMATCH_ORT_THREADS="${BERNMATCH_ORT_THREADS:-8}"

if ! mkdir -p "$DATA" 2>/dev/null || ! touch "$DATA/.write-test" 2>/dev/null; then
  echo "WARNING: $DATA is not writable; falling back to /home/user/data (NOT persistent)"
  DATA=/home/user/data
  export BERNMATCH_DATA_DIR="$DATA"
  mkdir -p "$DATA"
else
  rm -f "$DATA/.write-test"
fi

build_index() {
  rm -f "$DATA/build.failed"
  echo "$(date -u +%FT%TZ) build start" >> "$DATA/build.log"
  python -m app.search fetch-model --model small --model-dir "$DATA/models/e5-small" >> "$DATA/build.log" 2>&1 || return 1
  KNOW=""
  if [ -f "$DATA/knowledge/entities.jsonl" ] && [ -f "$DATA/knowledge/claims.jsonl" ]; then
    KNOW="--knowledge-dir $DATA/knowledge"
  fi
  # shellcheck disable=SC2086
  python -m app.search build --corpus-jsonl "$DATA/corpus.jsonl" $KNOW \
      --model-dir "$DATA/models/e5-small" --data-dir "$DATA" >> "$DATA/build.log" 2>&1 || return 1
  echo "$(date -u +%FT%TZ) build done" >> "$DATA/build.log"
}

if [ ! -f "$DATA/READY" ] && [ -f "$DATA/corpus.jsonl" ] && [ ! -f "$DATA/.building" ]; then
  (
    touch "$DATA/.building"
    if build_index; then :; else echo "$?" > "$DATA/build.failed"; fi
    rm -f "$DATA/.building"
  ) &
elif [ ! -f "$DATA/READY" ]; then
  echo "No READY marker and no $DATA/corpus.jsonl (or a build is running): serving 'not ready'."
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 7860
