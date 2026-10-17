# Optional API-backed language models

Local inference remains the default. No request is sent to an external provider merely by opening the application, discovering GGUF files, or saving an API connection. The administrator must explicitly select and activate an API profile.

## Configure

Open **Language models → Add an API model** in the existing model panel. Enter a descriptive connection name, provider model ID, and API key. Choose **OpenAI**, whose base URL is fixed to `https://api.openai.com/v1`, or **OpenAI-compatible API** and enter its HTTPS base URL, including `/v1` where required. The adapter uses bearer authentication and the Chat Completions protocol. Native Anthropic, Azure-specific routing/authentication, and providers with different protocols are not implemented.

Select strict JSON schema when supported. JSON object mode is available for compatible providers that do not accept JSON schema. The same application-side status, answer, citation, and response-language validation applies to both modes. There is no silent format downgrade, provider change, local fallback, or automatic network retry. Model availability and supported parameters depend on the provider and account.

Press **Save API model**. The key field is cleared and the new profile appears beside local models in the same dropdown; saving does not contact the provider. Select the profile, review the displayed destination, explicitly allow sending answer context, and press **Activate selected model**. Activation makes a small test generation with fixed application-generated text and no user documents. It can incur provider charges. Successful activation persists the selected profile ID in server settings; failed activation retains the previous model selection. Pending answers block switching.

Activation checks that authentication, the chosen model, and the selected JSON format work together. It does not certify domain accuracy, latency, account limits, or costs. Switching back to a local model clears the active API selection without deleting the saved connection.

## Data and credentials

In API mode the provider receives the grounding instructions, domain settings (including glossary), question, retrieved document passages, and recent conversation turns needed by the engine. The application keeps document storage and retrieval local, but this is **not a fully offline/private inference path**. A persistent provider notice is displayed for signed-in users. If the selected provider changes after a browser loaded its status, a question from that stale browser is rejected before generation; the page refreshes its provider notice and the user can review and resubmit. Server API clients may send the status response's `model.selection_id` as `model_selection` for the same check.

The API key is stored only in `data/cloud-models.json`, never returned by catalog/status endpoints, placed in prompts, or persisted to browser storage. On Windows it is protected by DPAPI for the Windows account running the server. A different server account or machine generally needs the key entered again. On POSIX this version uses a mode-0600 credential file (base64 encoding, **not encryption at rest**); protect that server account and its storage accordingly. API key files are deliberately excluded from application data backups, along with server settings and model registries. No key is written into the server's configuration file or database.

Only administrators can save and select connections; all modifying routes require CSRF verification. Outbound requests require HTTPS, reject redirects rather than forwarding credentials, bypass environment proxy settings, and do not reflect provider error bodies into user-facing errors or job logs. DNS, TLS trust and outbound internet access must be available to the server.

OpenAI requests set `store: false`; this is not a promise of zero provider-side retention. Review the chosen provider/account's actual data controls. Provider authentication, rate limits and billing remain the customer's responsibility. A grounded answer can require extra model calls for language or citation repair. Cancellation prevents publication after the provider response arrives; it does not guarantee that provider computation or billing stops mid-request.

Profiles in this version are added as new connections; to rotate a key, save and activate a new profile. No secret is revealed for editing. Provision keys through this local UI rather than pasting them into an assistant conversation.

## Verification and scope

Tests cover Windows credential protection and round-trip access, secret-free metadata, provider payloads, output truncation/malformed JSON, cancellation, sanitized errors, explicit consent, failed-activation rollback, stale-provider rejection, and the actual HTTP/engine path generating a cited answer against a simulated provider. No real key or document was sent to an external provider during development. A live provider acceptance test with the customer's key is still required.

The hardware calculator continues to estimate **local GPU deployments only**. It does not calculate API prices, quotas, cloud capacity, speech-to-text, or provider latency. Document embeddings remain local regardless of the answering model.

The implementation follows [OpenAI's Chat Completions API reference](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create) and [Structured Outputs documentation](https://developers.openai.com/api/docs/guides/structured-outputs). These document the request fields and structured output formats; compatibility with other providers requires their corresponding support.
