# Local API

Base: the local server, normally port 8095. JSON UTF-8 unless stated otherwise. Cookies are HTTP-only and SameSite Strict. POSTs after login require `X-CSRF-Token` returned by `/api/me`. Browser requests must be same-origin. The server API remains local; administrators may explicitly configure outbound API model connections with server-side credentials.

| Method | Path | Access / contract |
|---|---|---|
| GET | `/healthz` | Liveness and version only |
| GET | `/api/bootstrap` | Whether the initial account is needed |
| POST | `/api/setup` | Once only: `{code,username,password}`; local bootstrap code |
| POST | `/api/login` | `{username,password}`; sets session cookie |
| GET | `/api/me` | Current account and CSRF token |
| POST | `/api/logout` | End the current session |
| POST | `/api/password` | `{current,password}`; revoke all user's sessions |
| GET | `/api/status` | Domain, asset readiness, queue sizes, knowledge version |
| GET | `/api/dashboard` | Admin; document counts/status, active work, account counts, latest local backup time and up to ten failed/pending documents; no question text or credentials |
| GET | `/api/watched-folders` | Admin; registered server-local folders and proposed document changes |
| POST | `/api/watched-folders` | Admin + CSRF; `{path,recursive:true,restricted?:boolean}`; register a folder and initial policy for new files, no import |
| POST | `/api/watched-folders/{id}/scan` | Admin + CSRF; `{}`; bounded scan proposing changes only |
| POST | `/api/watched-folders/{id}/enabled` | Admin + CSRF; `{enabled:boolean}`; pause/resume automatic scanning |
| POST | `/api/watched-changes/{id}/approve` | Admin + CSRF; `{sha,confirm_archive?}`; reject stale source hashes, stage/index new content before publication; `sha:"missing"` plus `confirm_archive:true` archives an explicitly reviewed missing source |
| POST | `/api/watched-changes/{id}/ignore` | Admin + CSRF; `{sha}`; ignore that fingerprint, or `"missing"` |
| GET | `/api/reviews?kind=attention&state=open&before=...` | Admin; 50 saved review items plus pagination cursor; kind is attention/insufficient/clarify/incorrect/helpful/all, state is open/resolved/all |
| GET / POST | `/api/groups` | Admin; list groups/member IDs or create `{name,members:[user_id,...]}`; writes require CSRF |
| POST | `/api/groups/{id}` | Admin + CSRF; update name/membership; membership changes stop pending answers |
| POST | `/api/groups/{id}/delete` | Admin + CSRF; `{confirm:true}`; remove group and grants, keeping document restrictions |
| GET / POST | `/api/documents/{id}/access` | Admin; read policy or write `{restricted:boolean,groups:[group_id,...]}` with CSRF; restricted + no groups means administrators only |
| POST | `/api/watched-folders/{id}/access` | Admin + CSRF; `{restricted:boolean}`; initial policy for subsequently approved new files, existing documents retain their policy |
| POST | `/api/reviews/{message_id}` | Admin + CSRF; `{status:"open"\|"resolved",note?}`; review note up to 2,000 characters; later feedback reopens a resolved review |
| GET | `/api/capacity/catalog` | Authenticated; frozen offline model profiles and current deployment limits |
| POST | `/api/capacity/estimate` | Authenticated + CSRF; hypothetical hardware estimate, no deployment changes; see CAPACITY.md |
| GET | `/api/models` | Admin; real local GGUF files, active selection, runtime state, model directory |
| GET | `/api/models/folders?path=...` | Admin; browse local server directories and local drives; no file contents returned |
| POST | `/api/models/scan` | Admin + CSRF; `{path,recursive:true}`; discover valid GGUFs in a local folder; persist chosen folder; return model catalog and scan counts |
| POST | `/api/models/cloud` | Admin + CSRF; `{name,provider,model,api_key,base_url?,response_mode?}`; provider `openai` or `compatible`; save encrypted/private server credential and return secret-free profile/catalog; no outbound request |
| POST | `/api/models/register` | Admin + CSRF; `{path}` to an existing server-local GGUF; no download or copy |
| POST | `/api/models/activate` | Admin + CSRF; `{model_id,confirm_cloud?}` from catalog; `confirm_cloud:true` required for API models; reject busy answer queue, load and health-check before persisting; rollback on failure |
| POST | `/api/documents/import?filename=...&title=...` | Admin + CSRF; raw single-file body used by sequential folder import; optional `restricted=1` creates administrators-only documents; skip identical indexed content with the same initial scope or retry pending/failed content; returns `{skipped,document_id,job_id?}` |
| GET / POST | `/api/conversations` | List owned conversations / create with `{}` |
| GET | `/api/conversations/{id}/messages` | Owned saved messages and citations |
| POST | `/api/conversations/{id}/rename` | Owner + CSRF; `{title}`; trimmed title of 1–100 characters |
| POST | `/api/conversations/{id}/delete` | Owner + CSRF; `{confirm:true}`; reject queued/running answers; permanently remove messages, feedback and completed answer job copies; previous backups/exports remain |
| POST | `/api/ask` | `{conversation_id,question,response_language?,model_selection?}`; returns `{job_id}`; language is `en` or `fa` |
| GET | `/api/jobs/{id}` | Owned job: queued/running/done/failed/canceled |
| POST | `/api/jobs/{id}/cancel` | `{}`; cancel an owned job |
| POST | `/api/feedback` | `{message_id,rating,note?}`; helpful or incorrect, owned answer only |
| GET | `/api/documents` | Active document metadata; admins may add `?archived=1` |
| POST | `/api/documents?filename=...&title=...&priority=0` | Admin; raw file body, optional `restricted=1` records administrators-only access before indexing; returns document and indexing job IDs |
| GET | `/api/documents/{id}/download` | Authenticated download of active original |
| POST | `/api/documents/{id}/replace?filename=...` | Admin; raw file body; preserve prior revision |
| POST | `/api/documents/{id}/index` | Admin; retry indexing |
| POST | `/api/documents/{id}/archive` | Admin; remove from answers, retain data |
| POST | `/api/documents/{id}/restore` | Admin; reactivate archived document |
| POST | `/api/documents/{id}/delete` | Admin + CSRF; `{confirm:true}`; archived documents only; permanently remove document, file revisions, and chunks. Existing answer excerpts and prior backups remain. |
| POST | `/api/domain` | Admin; domain profile, see config/domain.json |
| GET / POST | `/api/users` | Admin; list / create `{username,password,role}` |
| POST | `/api/users/{id}/active` | Admin; `{active:boolean}`; cannot disable self |
| POST | `/api/backups` | Admin; `{}`; create snapshot and get local download URL |
| GET | `/api/backups/{filename}` | Admin; download a generated backup |

Answer jobs return `status` (answered/clarify/insufficient), `answer`, `citations`, `knowledge_version`, `domain_version`, `conversation_id` `message_id`, and `response_language`. Each citation has its passage number, document ID/version, location, original filename, title and supporting text. New answers also retain `access_documents` for server-side access checks across retrieved evidence and included history. These are provenance records, not calibrated confidence scores.

The bounded queue runs one language-model generation at a time. Cancelation is checked during streaming and before publishing an answer. Missing evidence returns an explicit insufficient result without loading the language model. Model or citation-contract failures produce a failed job rather than silently falling back to general knowledge.

Authenticated users see shared documents and restricted documents granted to their groups. Administrators can access all documents. Conversations, jobs and feedback are owner-scoped; administration is role-scoped. For LAN deployment TLS and an explicit allowed hostname are required. This is an internal API, not a publicly exposed hosted service.


## Android Wi-Fi gateway

Web-only local speech endpoints are documented in [SPEECH.md](SPEECH.md): authenticated status and short WAV transcription jobs, owner-scoped result/cancel/consume, and administrator-only settings. They are deliberately absent from the Android gateway allowlist. Voice transcripts do not automatically create chat messages.

The native Android project is in `../Soshyant Android`. Its optional TLS-only gateway normally runs on the selected Wi-Fi IPv4 address at port 8096 and forwards chat/login/history/status calls to the existing loopback server. Run `expert.mobile_gateway` with an explicit bind address, certificate, key and loopback backend, or use the Android project's START-WIFI.bat launcher. Administrative APIs are not exposed by the gateway. The same user sessions, conversation ownership and CSRF tokens apply; returned session cookies are marked Secure. Original phone Host/Origin are checked at the gateway; the trusted loopback hop uses the backend origin. The phone never needs a language-model provider key.
