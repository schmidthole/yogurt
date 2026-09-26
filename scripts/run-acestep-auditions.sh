#!/usr/bin/env bash
# Run after building the pinned ACE-Step image; restore the live generator on exit.
set -euo pipefail
repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
model_dir=${ACESTEP_MODEL_DIR:-$HOME/.local/share/yogurt-acestep/checkpoints}
output_dir=${AUDITION_OUTPUT_DIR:-$HOME/Music/yogurt-auditions}
mkdir -p "$model_dir" "$output_dir"
was_running=$(docker inspect -f '{{.State.Running}}' yogurt-generator)
restore_generator() {
  if [[ "$was_running" == true ]]; then
    docker start yogurt-generator >/dev/null
  fi
}
trap restore_generator EXIT
if [[ "$was_running" == true ]]; then
  docker stop yogurt-generator >/dev/null
fi
docker run --rm --name yogurt-acestep-audition --gpus all --shm-size 2g \
  --entrypoint /app/.venv/bin/python \
  -e ACESTEP_REVISION=ca1e85fe9430179831e6bc6be790c332190a3866 \
  -e PYTHONUNBUFFERED=1 -e TOKENIZERS_PARALLELISM=false \
  -v "$model_dir:/app/checkpoints" \
  -v "$output_dir:/output" \
  -v "$repo_dir/scripts/audition_acestep.py:/app/audition_acestep.py:ro" \
  yogurt-acestep:audition /app/audition_acestep.py
