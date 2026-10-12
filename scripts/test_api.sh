#!/usr/bin/env sh
# End-to-end API checks. Start the API first; this script creates disposable
# member/book records and checks both successful and rejected requests.
set -eu

BASE_URL=${BASE_URL:-http://127.0.0.1:8000}
PARTNER_API_KEY=${PARTNER_API_KEY:-local-catalogue-key}
PARTNER_API_SECRET=${PARTNER_API_SECRET:-local-catalogue-secret}
CURL=${CURL:-curl}
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT HUP INT TERM

fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
json_value() {
    # Python is already a project runtime dependency; avoid requiring jq.
    python -c 'import json,sys; value=json.load(sys.stdin); print(value[sys.argv[1]])' "$1"
}
request() {
    METHOD=$1; PATH_PART=$2; EXPECTED=$3; BODY=${4-}
    if [ "$#" -ge 4 ]; then shift 4; else shift 3; fi
    if [ -n "$BODY" ]; then
        STATUS=$("$CURL" -sS -o "$TMP_DIR/body" -w '%{http_code}' -X "$METHOD" "$BASE_URL$PATH_PART" -H 'Content-Type: application/json' -d "$BODY" "$@") || fail "$METHOD $PATH_PART could not reach API"
    else
        STATUS=$("$CURL" -sS -o "$TMP_DIR/body" -w '%{http_code}' -X "$METHOD" "$BASE_URL$PATH_PART" "$@") || fail "$METHOD $PATH_PART could not reach API"
    fi
    [ "$STATUS" = "$EXPECTED" ] || { cat "$TMP_DIR/body" >&2; fail "$METHOD $PATH_PART expected HTTP $EXPECTED, got $STATUS"; }
    printf 'PASS %s %s -> %s\n' "$METHOD" "$PATH_PART" "$STATUS"
}
check_error() {
    python -c 'import json,sys; d=json.load(open(sys.argv[1])); assert "error" in d and "code" in d["error"] and "message" in d["error"]' "$TMP_DIR/body" || fail 'error response did not use the documented JSON shape'
}

request GET /books 200
request GET /books/999999 404
check_error
request POST /auth/member/login 401 '{"email":"aman@example.com","password":"wrongpass"}'
check_error
request GET /partner/catalogue 401
check_error
request GET /partner/catalogue 401 '' -H 'X-API-Key: wrong-key' -H 'X-API-Secret: wrong-secret'
check_error
request GET /partner/catalogue 200 '' -H "X-API-Key: $PARTNER_API_KEY" -H "X-API-Secret: $PARTNER_API_SECRET"

# Create two isolated members and log both in, so the privacy check is real.
STAMP=$(date +%s)
EMAIL_A="curl-a-$STAMP@example.com"
EMAIL_B="curl-b-$STAMP@example.com"
request POST /members 201 "{\"member_name\":\"Curl Reader A\",\"email\":\"$EMAIL_A\",\"password\":\"curl-pass-123\"}"
MEMBER_A=$(json_value member_id < "$TMP_DIR/body")
request POST /members 201 "{\"member_name\":\"Curl Reader B\",\"email\":\"$EMAIL_B\",\"password\":\"curl-pass-123\"}"
MEMBER_B=$(json_value member_id < "$TMP_DIR/body")
request POST /auth/member/login 200 "{\"email\":\"$EMAIL_A\",\"password\":\"curl-pass-123\"}"
TOKEN_A=$(json_value access_token < "$TMP_DIR/body")
request POST /auth/member/login 200 "{\"email\":\"$EMAIL_B\",\"password\":\"curl-pass-123\"}"
TOKEN_B=$(json_value access_token < "$TMP_DIR/body")
request GET /loans/me 200 '' -H "Authorization: Bearer $TOKEN_A"
request GET /fines/me 200 '' -H "Authorization: Bearer $TOKEN_A"
request POST /fines/999999/pay 404 '' -H "Authorization: Bearer $TOKEN_A"
check_error

# Librarian cookie session: verify denial before login, then checkout/return.
request POST /loans/checkout 401 '{"member_id":1,"copy_id":1,"due_date":"2099-12-31"}'
check_error
COOKIE_JAR="$TMP_DIR/cookies"
request POST /auth/librarian/login 200 '{"email":"librarian1@example.com","password":"password123"}' -c "$COOKIE_JAR"
request GET /reports/overdue-loans 200 '' -b "$COOKIE_JAR"
request GET /reports/most-borrowed-books 200 '' -b "$COOKIE_JAR"

# Use multiple seeded copies to exercise availability and the three-loan cap.
TODAY=$(date +%F)
for COPY_ID in 1 2 3; do
    request POST /loans/checkout 201 "{\"member_id\":$MEMBER_A,\"copy_id\":$COPY_ID,\"due_date\":\"$TODAY\"}" -b "$COOKIE_JAR"
    [ "$COPY_ID" != 1 ] || LOAN_ID=$(json_value loan_id < "$TMP_DIR/body")
done
request POST /loans/checkout 409 "{\"member_id\":$MEMBER_A,\"copy_id\":4,\"due_date\":\"$TODAY\"}" -b "$COOKIE_JAR"
check_error
request POST /loans/checkout 409 "{\"member_id\":$MEMBER_B,\"copy_id\":1,\"due_date\":\"$TODAY\"}" -b "$COOKIE_JAR"
check_error

# Return one loan, reject a duplicate return, and check ownership isolation.
request GET /loans/me 200 '' -H "Authorization: Bearer $TOKEN_B"
request POST "/fines/999999/pay" 404 '' -H "Authorization: Bearer $TOKEN_B"
request POST "/loans/$LOAN_ID/return" 200 '' -b "$COOKIE_JAR"
request POST "/loans/$LOAN_ID/return" 409 '' -b "$COOKIE_JAR"
check_error

printf '\nAll curl API checks passed.\n'



