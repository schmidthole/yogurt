#!/usr/bin/env bash
# Benchmark an isolated output queue, restoring the live generator on exit.
set -euo pipefail
model=${1:?supply the DiT model}
lm=${2:?supply the music language model}
quantization=${3:-none}
output_dir=${4:?supply an empty benchmark output directory}
repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
mkdir -p "$output_dir"
if [[ -n "$(ls -A "$output_dir")" ]]; then
  echo 'Benchmark output directory must be empty' >&2
  exit 1
fi
was_running=$(docker inspect -f '{{.State.Running}}' yogurt-generator)
restore_generator() {
  if [[ "$was_running" == true ]]; then docker start yogurt-generator >/dev/null; fi
}
trap restore_generator EXIT
if [[ "$was_running" == true ]]; then docker stop yogurt-generator >/dev/null; fi
docker run --rm --name yogurt-model-benchmark --gpus all --memory=24g --memory-swap=28g \
  -e ACESTEP_DIT_MODEL="$model" -e ACESTEP_LM_MODEL="$lm" -e ACESTEP_QUANTIZATION="$quantization" \
  -v /var/yogurt-generator:/data -v "$output_dir:/radio" \
  -v "$repo_dir/generator/acestep.py:/app/generator/acestep.py:ro" \
  -v "$repo_dir/scripts/benchmark_acestep.py:/app/benchmark_acestep.py:ro" \
  yogurt-generator python /app/benchmark_acestep.py
