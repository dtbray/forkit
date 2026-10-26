# Kitchen ingredients and dinner planning

Proposed next feature for the household fork; not implemented by the initial lab deployment.

1. Connect a ChatGPT account through the official Sign in with ChatGPT open-source OAuth flow. Keep PKCE, state validation, session binding, token refresh, disconnect, and server-side credential storage in the backend. Do not borrow a Codex client ID or read local Codex credentials.
2. Explicitly select/upload a kitchen photo. Explain that the image is sent to OpenAI before submission. Bound file size, decode and validate image content, strip metadata, and avoid retaining originals by default.
3. Extract structured ingredient suggestions, with uncertain items clearly marked. Let the user correct names and confirm quantities/units; a photo cannot establish hidden contents, freshness, or exact amounts.
4. Save only confirmed items to a persistent household pantry, with optional later Grocy integration. Do not silently overwrite Grocy stock.
5. Match saved recipes against confirmed pantry amounts. Show a strict "Cook tonight without shopping" list only when every required ingredient and quantity is covered. Treat optional ingredients explicitly. Keep recipes with missing or unknown quantities in a separate list, and never assume staples are available.

Identity, permission to use the ChatGPT plan, and recipe-app access control are separate concerns. Verify account eligibility and supported image models during implementation, and offer a clear disconnected/unavailable state. Tests should cover OAuth state/replay, token isolation, upload validation, review-before-save, units, ingredient aliases, missing ingredients, and unknown quantities.

Official references:
- https://developers.openai.com/siwc/quickstart
- https://developers.openai.com/api/docs/guides/images-vision
