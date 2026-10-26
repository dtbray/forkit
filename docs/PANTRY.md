# Kitchen ingredient ingest

`/pantry` is a shared household ingredient list in Forkit's existing SQLite DB
(migration 0006). It does not sync Grocy, consume stock, or infer quantities.

- Type a list or focus the ordinary text field and use your phone keyboard's
  microphone. Commas, newlines, “and”, and spoken “next item” separate entries.
  No Web Speech API, microphone recording, or audio upload is used by Forkit.
- Take a camera photo or select an existing image. Browser decoding supports the
  formats available on the device; unsupported HEIC files explain how to retry
  with JPEG. The browser resizes to 2048px, converts to JPEG and strips metadata.
  The server independently validates/normalizes the image, rejects animation,
  caps uploads at 8 MB / 25 megapixels, limits requests to 5/minute, and keeps
  only two recognition calls active with a 90-second total deadline.
- Both paths produce editable candidates, never stock changes. Confirm names,
  amounts, units and notes; uncheck incorrect candidates; explicitly add to pantry.
  Failed saves retain the entire review. Duplicate canonical names keep existing
  amounts and never increment inventory. Remove unavailable ingredients manually.
- Recipe matches are conservative full ingredient names, with a short explicit
  list of common food plurals. No substring/fuzzy matching, guessed substitutions,
  assumed staples or quantity/safety guarantees. All missing names are shown.

## ChatGPT plan connection

Photo recognition uses **Sign in with ChatGPT**, not a paid API key and not Codex
credentials. It follows OpenAI's supported open-source client registration and
[self-hosted VM procedure](https://developers.openai.com/siwc/token-sharing-open-source/self-hosted-vms).
The existing Authentik household login still protects the lab app. Household
photo requests use the connected owner's ChatGPT plan and its usage limits.

The official OSS flow uses a **127.0.0.1 callback on the browser's computer**.
The initial sign-in cannot be completed by a browser on a phone talking directly
to a remote lab server. Use the helper on a desktop/laptop once; the server owns
subsequent token refreshes. Standard website identity-only sign-in is a separate
registered-client flow and does not by itself grant plan inference.

On the computer running your browser, check out this fork and run:

```sh
uv run --with 'PyJWT[crypto]>=2.10,<3' --with 'httpx>=0.27,<1' \
  backend/src/forkit/chatgpt.py
```

The helper starts the loopback listener before opening **Continue with ChatGPT**.
Choose the account/workspace and authorize plan use. It requests
`openid profile email offline_access resource.invoke chatgpt.tokens.use.direct`,
uses dynamic client registration with a stable host ID, state, nonce and S256
PKCE, exchanges with the issued client ID, validates the ID token's signature,
issuer, audience, expiry and nonce, and writes an owner-only file at
`~/.config/forkit/chatgpt.json`. A returning connection must match its original
issued client ID and verified subject. No tokens appear in the browser app,
console logs, source control or URL query parameters. The authorization URL
contains one-time state/nonce/challenge, not access or refresh tokens.

Transfer only that protected credential file to the lab over SSH, then install
inside the `forkit` guest as UID/GID 1000 at:

```text
/opt/homelab/forkit/data/chatgpt/credentials.json   mode 0600
/opt/homelab/forkit/data/chatgpt/                    mode 0700
```

This maps to `/data/chatgpt/credentials.json` in the web container. The operator
can override it with `FORKIT_CHATGPT_CREDENTIALS_PATH`. Keep the VM's own stable
host ID separate when transferring a registration; do not overwrite a VM ID
with the laptop's. The current preview does not provide transferred-session
host-specific attribution/revocation (see the official VM guide).

After installing the file, open Pantry, check the connection, and choose an
image-capable model from the **live account-specific model catalog**. No model
or entitlement is invented or silently substituted. A recognized image is sent
only after the person selects it. Photos are not written to persistent storage.
Only reviewed ingredient fields are saved. Unsupported models, missing grants,
expired/revoked connections, limits and interrupted output return visible errors.

The server serializes refreshes with an OS file lock and atomically replaces
access token, expiry, scopes and rotating refresh token together. Credential
files with group/world access are rejected. The whole-project backup contains
this protected file inside the existing encrypted Restic backups; treat restored
credentials as sensitive and disconnect the grant if a backup is compromised.

**Disconnect ChatGPT** removes the local credential record. To revoke the remote
grant or manage limits, use [ChatGPT usage/access settings](https://chatgpt.com/settings/usage).
Changing users requires a new, explicitly authorized local connection.

## API and validation

- `GET /api/pantry`, `GET /api/pantry/recipes`
- `POST /api/pantry/preview/text` with `{text}`
- `POST /api/pantry/preview/photo` with a raw JPEG/PNG/WebP body
- `POST /api/pantry/items` with `{source: "text" | "photo", items: [...]}`
- `DELETE /api/pantry/items/{id}`
- `GET /api/pantry/capabilities`, `GET /api/pantry/chatgpt/models`
- `PUT /api/pantry/chatgpt/model` with `{model: slug}`
- `DELETE /api/pantry/chatgpt`

Tests use migrated isolated databases, signed test identities, fake provider
streams and real browser camera-file input/canvas processing. No real pantry
photos or household inventory are used as test data. Physical iPhone camera,
keyboard dictation, HEIC decoding and live ChatGPT consent/recognition remain
household acceptance checks until performed on actual devices.

Primary integration references:
[Registration/sign-in](https://developers.openai.com/siwc/token-sharing-open-source/sign-in),
[Models/inference](https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference),
[Refresh/security](https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions),
[Preview constraints](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations).
