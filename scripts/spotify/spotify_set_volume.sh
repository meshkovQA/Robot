#!/usr/bin/env bash
set -euo pipefail
pct="${1:-}"
[[ -z "$pct" ]] && { echo "usage: $0 <0..100>"; exit 2; }
# playerctl volume принимает 0..1
float=$(awk -v p="$pct" 'BEGIN{ printf("%.2f", p/100) }')
playerctl --player=spotify volume "$float"
echo "OK"