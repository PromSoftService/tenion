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

## Contact requests

`POST /api/contact` accepts a name, email, message and one of the supported
request topics. The enquiry forms on the site deliver the message to the
address configured in `TENION_CONTACT_RECIPIENT`; the visitor's email is set as
`Reply-To` so the team can answer directly.

Contact names, email addresses and message text are not stored in Tenion's
database. Only short-lived HMAC hashes and timestamps are retained for rate
limiting. The endpoint uses the same origin check, input validation and
honeypot protection as registration.

## Administration

The unlinked `/admin/` interface lists MetaPlatform users and can permanently
delete an account through the loopback-only MetaPlatform Admin API. It uses the
same password as that API, but the password is submitted only during login and
is never stored in browser storage. Tenion creates a time-limited random admin
session in an HttpOnly, Secure, SameSite=Strict cookie. Session tokens are
stored only as HMAC hashes; destructive requests additionally require a CSRF
token and an exact same-origin request.

Deleting a MetaPlatform user also removes the matching registration
record from Tenion so the email and username can be registered again. The UI
requires the administrator to type the exact username before enabling the
irreversible action. Failed admin logins are rate-limited per IP.

Store the Yandex Mail application password on the server without placing it in
shell history or chat:

```bash
sudo python3 /srv/pss/apps/tenion/deploy/configure_smtp.py
```

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
- Team and implementation enquiries open the contact form and are delivered to
  `info@promsoftservice.ru` by the server.
- “First start” and “Download center” stay disabled until their content is ready.
