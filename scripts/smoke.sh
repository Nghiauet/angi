#!/usr/bin/env bash
# Live smoke test — requires the app on 127.0.0.1:46405 (Ollama optional: canned floor).
set -u
BASE="${BASE:-http://127.0.0.1:46405}"
fail=0

check() {
  local name="$1" expected="$2" actual="$3"
  if [[ "$actual" == *"$expected"* ]]; then
    echo "PASS: $name"
  else
    echo "FAIL: $name — expected '$expected' in output"
    fail=1
  fi
}

check "health" '"status":"ok"' "$(curl -s "$BASE/health")"
check "homepage" "Hôm nay ăn gì" "$(curl -s "$BASE/")"
check "og image" "image/png" "$(curl -sI "$BASE/og.png" | tr -d '\r')"

out=$(curl -s -X POST "$BASE/api/suggest" -H 'Content-Type: application/json' \
  -d '{"budget": "50", "mood": "vui", "rejected": []}' --max-time 60)
check "suggest: has dish" '"dish"' "$out"
check "suggest: tier 0" '"tier":0' "$out"

out=$(curl -s -X POST "$BASE/api/suggest" -H 'Content-Type: application/json' \
  -d '{"rejected": ["Phở bò","Bún chả","Cơm tấm sườn bì chả","Bánh mì ốp la","Xôi xéo","Cháo gà"]}' --max-time 60)
check "suggest: 6 rejections -> tier 3" '"tier":3' "$out"

out=$(curl -s -X POST "$BASE/api/suggest" -H 'Content-Type: application/json' \
  -d '{"budget": "20"}' --max-time 60)
check "suggest: budget 20 -> price_tier 1" '"price_tier":1' "$out"
check "suggest: broke flag present" '"broke":' "$out"

rejected16=$(python3 -c 'import json; print(json.dumps({"rejected": ["x"] * 16}))')
out=$(curl -s -X POST "$BASE/api/suggest" -H 'Content-Type: application/json' \
  -d "$rejected16" --max-time 60)
check "suggest: 16 rejections -> tier 5" '"tier":5' "$out"

out=$(curl -s "$BASE/api/weather?city=hn" --max-time 10)
check "weather endpoint" '"weather":' "$out"
code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/api/weather?city=paris")
check "weather 400 on bad city" "400" "$code"

code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/api/suggest" \
  -H 'Content-Type: application/json' -d 'not json')
check "400 on malformed body" "400" "$code"

if [[ $fail -eq 0 ]]; then
  echo "--- ALL SMOKE TESTS PASSED ---"
else
  echo "--- SMOKE TESTS FAILED ---"
fi
exit $fail
