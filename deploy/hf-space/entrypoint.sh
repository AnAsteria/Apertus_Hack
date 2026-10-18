#!/bin/sh
# Hugging Face Space start-up. Serves the app at once; builds or restores the search index in
# the background. Heavy work runs on the container's LOCAL disk; the persistent bucket (/data) only
# holds durable files, because live SQLite databases do not belong on a mounted bucket.
#
# Durable store (/data, the bucket):
#   bundle.tar.gz     a finished index (READY + indexes/<gen> + corpus.sqlite link): restored on every start
#   corpus.jsonl      T06 export used for the build (public data)
#   knowledge/        optional T08 output (entities.jsonl + claims.jsonl) for the same corpus
#   pipeline.log      progress log, pipeline.failed holds the failing stage name
#
# Restart: if bundle.tar.gz exists it is extracted and nothing else runs.
# First run: only when BERNMATCH_AUTO_PIPELINE=1 (a Space variable; off by default, off in CI):
#   crawl (final profile, 8 sources at once) -> export -> T08 rules-only -> fetch model -> build
#   -> package -> store the bundle. Inputs already present in /data (corpus.jsonl, knowledge/) are
#   used instead of being recomputed. To rebuild: delete bundle.tar.gz (and pipeline.failed).
set -u
STORE="${BERNMATCH_STORE_DIR:-/data}"
WORK="${BERNMATCH_WORK_DIR:-/home/user/work}"
SERVE="${BERNMATCH_SERVE_DIR:-/home/user/serve}"
export BERNMATCH_DATA_DIR="$SERVE"
export BERNMATCH_ORT_THREADS="${BERNMATCH_ORT_THREADS:-8}"
mkdir -p "$WORK" "$SERVE"

store_ok=0
if mkdir -p "$STORE" 2>/dev/null && touch "$STORE/.write-test" 2>/dev/null; then
  rm -f "$STORE/.write-test"; store_ok=1
else
  echo "WARNING: $STORE is not writable; results will NOT be persisted"
fi

LOG="$WORK/pipeline.log"
log() { echo "$(date -u +%FT%TZ) $*" | tee -a "$LOG"; [ "$store_ok" = 1 ] && cp "$LOG" "$STORE/pipeline.log" 2>/dev/null; return 0; }

restore_bundle() {
  tar -xzf "$STORE/bundle.tar.gz" -C "$SERVE" && log "restored index bundle from $STORE/bundle.tar.gz"
}

fail() { log "FAILED at stage: $1"; [ "$store_ok" = 1 ] && echo "$1" > "$STORE/pipeline.failed"; return 1; }

# Print "build progress: N of M entries embedded (P%)" from the last progress line the builder wrote.
progress_line() {
  line=$(grep -o '"embedded_entries": [0-9]*, "total_entries": [0-9]*' "$WORK/build.err" 2>/dev/null | tail -1)
  [ -n "$line" ] || return 0
  echo "$line" | awk -F'[:,]' '{ pct = ($4 > 0) ? 100 * $2 / $4 : 0; printf "build progress: %d of %d entries embedded (%.0f%%)\n", $2, $4, pct }'
}

pipeline() {
  cd "$HOME/app" || return 1
  CORPUS="$WORK/corpus"

  if [ -f "$STORE/corpus.jsonl" ]; then
    log "using existing $STORE/corpus.jsonl (skipping crawl)"
    cp "$STORE/corpus.jsonl" "$WORK/corpus.jsonl"
  else
    log "stage crawl: final profile, 8 sources at once"
    python -m app.ingest crawl --profile final --workers 8 --data-dir "$CORPUS" > "$WORK/crawl.out" 2> "$WORK/crawl.err" || fail crawl || return 1
    log "crawl done: $(grep -c stored_version_id "$WORK/crawl.err") page versions stored"
    python -m app.ingest export --data-dir "$CORPUS" > "$WORK/corpus.jsonl" 2>> "$LOG" || fail export || return 1
    [ "$store_ok" = 1 ] && cp "$WORK/corpus.jsonl" "$STORE/corpus.jsonl"
    log "exported corpus.jsonl ($(wc -c < "$WORK/corpus.jsonl") bytes)"
  fi

  KNOW=""
  if [ -f "$STORE/knowledge/entities.jsonl" ] && [ -f "$STORE/knowledge/claims.jsonl" ]; then
    log "using existing $STORE/knowledge"
    mkdir -p "$WORK/knowledge" && cp "$STORE/knowledge/"*.jsonl "$WORK/knowledge/"
    KNOW="--knowledge-dir $WORK/knowledge"
  elif [ -f "$CORPUS/corpus.sqlite" ]; then
    log "stage T08 (entity resolution, rules only; no AI key needed)"
    if python -m app.grounding --data-dir "$CORPUS" --no-judge >> "$LOG" 2>&1 \
       && [ -f "$CORPUS/knowledge/entities.jsonl" ] && [ -f "$CORPUS/knowledge/claims.jsonl" ]; then
      KNOW="--knowledge-dir $CORPUS/knowledge"
      [ "$store_ok" = 1 ] && mkdir -p "$STORE/knowledge" && cp "$CORPUS/knowledge/"*.jsonl "$STORE/knowledge/"
    else
      log "T08 failed or produced no files; continuing evidence-only"
    fi
  fi

  log "stage model: fetch pinned multilingual-e5-small"
  python -m app.search fetch-model --model small --model-dir "$WORK/models/e5-small" >> "$LOG" 2>&1 || fail model || return 1

  log "stage build: index (8 threads); a percentage is printed every 30 seconds"
  touch "$WORK/.building"
  ( while [ -f "$WORK/.building" ]; do sleep 30; progress_line; done ) &
  # shellcheck disable=SC2086
  python -m app.search build --corpus-jsonl "$WORK/corpus.jsonl" $KNOW \
      --model-dir "$WORK/models/e5-small" --data-dir "$SERVE" > "$WORK/build.out" 2> "$WORK/build.err"
  rc=$?
  rm -f "$WORK/.building"
  progress_line
  cat "$WORK/build.out" >> "$LOG"; tail -n 20 "$WORK/build.err" >> "$LOG"
  [ "$rc" = 0 ] || fail build || return 1

  log "stage package: bundle for restarts"
  python -m app.search package --data-dir "$SERVE" --output "$WORK/bundle.tar.gz" >> "$LOG" 2>&1 || fail package || return 1
  if [ "$store_ok" = 1 ]; then
    cp "$WORK/bundle.tar.gz" "$STORE/bundle.tar.gz.tmp" && mv "$STORE/bundle.tar.gz.tmp" "$STORE/bundle.tar.gz" \
      && log "bundle stored in $STORE ($(wc -c < "$WORK/bundle.tar.gz") bytes)" || log "WARNING: could not store the bundle"
  fi
  rm -f "$STORE/pipeline.failed"
  log "pipeline complete; search is live"
}

if [ "$store_ok" = 1 ] && [ -f "$STORE/bundle.tar.gz" ]; then
  restore_bundle || log "WARNING: bundle restore failed"
elif [ "${BERNMATCH_AUTO_PIPELINE:-0}" = "1" ]; then
  if [ "$store_ok" = 1 ] && [ -f "$STORE/pipeline.failed" ]; then
    log "previous pipeline failed at stage $(cat "$STORE/pipeline.failed"); not retrying automatically (delete $STORE/pipeline.failed to retry)"
  else
    ( pipeline ) &
  fi
else
  echo "No bundle and BERNMATCH_AUTO_PIPELINE is not 1: serving 'not ready'."
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 7860
