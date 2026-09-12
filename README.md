# Tenion portal

Public product portal for MetaPlatform at `tenion.cloud`.

The portal consists of:

- a dependency-free static site in `public/`;
- a private server-side registration service in `backend/`;
- an independent production Compose definition in `deploy/`.

For a local preview, serve that directory with any static HTTP server.

## Registration

`POST /api/register` accepts an email, a requested MetaPlatform username and an
explicit consent flag. The service:

1. creates a 12-character cryptographically random password;
2. hashes it with the exact MetaPlatform Argon2id policy;
3. creates a disabled account through the loopback-only MetaPlatform admin API;
4. sends the credentials by SMTP;
5. enables the account only after SMTP accepts the message.

Tenion stores only the email, username, delivery status and timestamps in its
own SQLite database. Plaintext passwords and password hashes are never stored
by Tenion. MetaPlatform remains the source of truth for authentication.

The public endpoint checks the request origin, rejects oversized/invalid input,
uses a honeypot and applies per-IP and per-email rate limits. Secrets are read
only from the production environment and must never be committed.

Run the tests from the repository root:

```bash
PYTHONPATH=backend python -m pytest -q backend/tests
```

Build the API image from the repository root:

```bash
docker build -f backend/Dockerfile -t pss-tenion-api:COMMIT .
```

## Conversion paths

- Free-access calls to action lead to the registration form.
- Existing users can open `app.tenion.cloud` directly.
- Team and implementation enquiries use `mailto:info@promsoftservice.ru`.
- “First start” and “Download center” stay disabled until their content is ready.
