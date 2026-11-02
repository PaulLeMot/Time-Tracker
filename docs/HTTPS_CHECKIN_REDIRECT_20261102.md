# HTTPS attendance redirect correction, 2026-11-02

The employee attendance client posts to `/api/timelog`; FastAPI canonicalizes it
to `/api/timelog/` with a307 response. Behind the TLS gateway, the upstream
produced `Location: http://operportal.fandocraft.ru:8443/api/timelog/`. The browser
cannot follow this HTTP downgrade from the HTTPS page. Direct HTTP remains valid.
Malformed JSON probes reproduced the routing failure without creating attendance.

The gateway now rewrites only absolute HTTP redirects for its own exact
`operportal.fandocraft.ru:8443` origin to HTTPS. Status307, path, query, request
method and body remain unchanged. External and relative redirects are unaffected.
See nginx's [proxy_redirect documentation](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_redirect).

No application routes, attendance logic, frontend, authentication, database,
jobs, TLS certificate, old HTTP listener or Next instance change. Existing open
browser tabs benefit from the gateway correction without new client JavaScript.
The camera1.1 task agreed to keep its work local until this incident is resolved,
then refresh main and preserve this configuration change.

Regression: `test_https_proxy_redirect.py` runs the actual nginx image with a
synthetic loopback-only upstream and temporary loopback TLS listener. It checks
redirect origin,307POST method/body, encoded paths/query, external/relative
redirects, and the existing root login redirect. No valid production attendance
request is used. The existing TLS key is mounted read-only and never exported.

Deployment: clean main-only fast-forward, compare exact changed file hashes,
save previous gateway config privately, run nginx syntax validation, atomically
replace only gateway config, test again, send graceful HUP to `operportal-https`.
Do not restart/rebuild the legacy app or DB. Validate live HTTP/HTTPS redirects
and malformed-body422 responses, original app start/restart metadata and safe
page/API parity. Publishing a commit and installing it are separate facts; the
incident receipt records the actual server SHA and completed checks.

Rollback: restore only the backed-up gateway config atomically and graceful-HUP
the gateway if verification fails; preserve production data. Reconcile any
rollback with a reviewed main-only revert before a subsequent deployment. Never
restore an old database snapshot for this routing change.
