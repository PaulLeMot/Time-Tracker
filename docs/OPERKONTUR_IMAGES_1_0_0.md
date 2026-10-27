# Image catalog integration 1.0.0

Adds `POST /api/integrations/operkontur/images/sync` for a signed, additive catalog exchange. Existing manual `/api/products/import` and its Excel format remain unchanged. No schema migration is required.

The sender supplies version 1, a 32-character hexadecimal job ID and unique products with five-digit `code`, `product_type`, nullable `fandom`, `name`, and JPEG `sha256`. The receiver checks its configured image folder for `code.jpg`, rejects missing/different/non-JPEG files, and inserts or updates only accepted codes. Existing product IDs and unrelated catalog rows are preserved. Repeated identical requests do not create duplicates. Transactions serialize against concurrent manual import; the manual import still replaces its catalog by design.

Authentication uses HMAC-SHA256 of `OKIMG1\n<TIME>\n` followed by the exact UTF-8 request body. Headers: `X-OperKontur-Time` (Unix seconds, ±120 seconds) and `X-OperKontur-Signature` (hex). Requests are limited to 8 MiB and 20,000 products. Replayed identical valid requests within the short window are harmless additive updates; no destructive action or deletion is supported.

Provision a random shared secret of at least 32 bytes in `/app/.operkontur-images.key`, readable only by the application user. The sender stores its copy outside source control in protected storage. Optional environment variables: `OPERKONTUR_IMAGES_KEY_FILE` and `OPERKONTUR_IMAGES_ROOT` (default `/app/static/img`). Never commit secrets; the local key is excluded from Git and Docker build context. An absent key disables the endpoint with HTTP 503. Use TLS when crossing an untrusted network.

The response reports `added`, `updated`, `unchanged`, and per-code `rejected` reasons. The sender records these independently of image-copy and FTP outcomes.

An optional signed `mode` is `upsert` (default, normal export scope) or `missing_only` (full catalog reconciliation). The latter inserts absent codes while preserving metadata of existing rows. Both verify ready images and never delete products.

`POST /api/integrations/operkontur/images/availability` accepts the signed literal body `{}` and returns numeric JPEG codes from the configured ready-image folder. It only lists files, does not touch the database, and supports the sender's 250px thumbnail presence filter when its HTTP process cannot access SMB. Actual image bytes continue to use the existing static route.

Validation: `python -m unittest test_operkontur_images_sync.py`. Tests use temporary synthetic files and no working database. Deployment should verify the existing manual route is unchanged and test a limited authorized catalog selection without importing the old Excel automatically.
