#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "Usage: $0 --site <dedicated-test-site>"
    echo "Runs the Accounts SaaS tenant-isolation release gate on a bench test site."
}

if [[ "${1:-}" != "--site" || -z "${2:-}" || -n "${3:-}" ]]; then
    usage >&2
    exit 2
fi

site_name="$2"
case "$site_name" in
    *test*|*staging*|localhost) ;;
    *)
        echo "Refusing to run destructive fixtures on non-test-looking site: $site_name" >&2
        echo "Use a dedicated site name containing 'test' or 'staging'." >&2
        exit 2
        ;;
esac

if ! command -v bench >/dev/null 2>&1; then
    echo "bench was not found on PATH" >&2
    exit 127
fi

bench --site "$site_name" run-tests --app reckon_accounts_saas \
    --module reckon_accounts_saas.tests.test_tenant_isolation
