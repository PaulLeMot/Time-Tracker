# Image catalog integration1.1.0

Adds signed POST `/api/integrations/operkontur/images/inventory`: body `{"codes":["00123"]}`; returns product metadata and `has_image` from one directory listing. No image hashing/decoding or database writes. Existing HMAC authentication, key-file configuration and replay window apply. Unique five-digit codes only; bounded body, database reads in1000-code groups.

The client compares metadata/presence first, then prepares only missing/changed entries and sends existing `/sync` requests in batches of100. This avoids full image reads before discovering an unavailable server. Existing sync semantics, manual Excel import, schema, credentials and image files are unchanged.

Validation: seven isolated unit tests, including inventory validation, authentication, additive update and image eligibility. Deploy by fast-forwarding the integration branch and rebuilding/restarting only the application container with existing configuration. No database migration.
