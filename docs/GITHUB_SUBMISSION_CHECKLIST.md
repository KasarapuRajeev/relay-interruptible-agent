# GitHub Submission Checklist

Last updated: September 30, 2026

Confirmed GitHub owner: [`KasarapuRajeev`](https://github.com/KasarapuRajeev)

Confirmed repository visibility: **Public**

Confirmed repository: [`KasarapuRajeev/relay-interruptible-agent`](https://github.com/KasarapuRajeev/relay-interruptible-agent)

| Required item | Status | Repository evidence / next action |
|---|---|---|
| Source Code | Published | Public `main` branch contains `relay/`, `web/`, `tests/`, `scripts/`, and `pyproject.toml` |
| Presentation | Completed externally; upload pending | Team confirmed the deck is finished; add the editable file or permitted share link |
| Video | Pending | Record the validated interruption scenario and add the final share link to the README |
| AI Disclosure | Ready locally | `AI_DISCLOSURE.md` |
| README | Ready locally | `README.md`; add team/repository/video details before final tag |
| APK/SDK (if any) | Not applicable | Relay is a Python web/CLI runtime; no Android APK or distributable SDK is currently produced |
| TAG | Pending publication | Create an annotated tag only after final tests and artifact links, suggested name: `v1.0.0-submission` |
| Other | Backend deployed | Validation report, execution plan, unique-product plan, teammate handoff, and [live Render API](https://relay-interruptible-agent-api.onrender.com) |

## Repository publication gate

- [x] Receive the GitHub username or organization name: `KasarapuRajeev`.
- [x] Confirm repository name: `relay-interruptible-agent`.
- [x] Confirm repository visibility: public.
- [ ] Confirm the final team/member names and college name.
- [x] Re-run all 79 automated tests after production proxy and tool-boundary validation.
- [x] Re-run the API-key and credential scan; no tracked secret was found.
- [x] Create the first reviewed commit: `a1bd394`.
- [x] Create the public GitHub repository without committing any secret.
- [x] Push the default `main` branch to GitHub.
- [ ] Add the completed presentation file/link and the pending video link.
- [ ] Verify README instructions on a clean machine.
- [ ] Create and push the final annotated submission tag.

## Proposed GitHub layout

```text
relay-interruptible-agent/
├── relay/                         # Runtime and provider adapters
├── web/                           # Demonstration dashboard
├── tests/                         # Automated validation suite
├── scripts/                       # Secure local startup scripts
├── docs/                          # Plans, validation, and submission material
├── AI_DISCLOSURE.md               # Required transparent AI-use statement
├── PROJECT_NOTES.md               # Detailed engineering log
├── TEAM_HANDOFF.md                # Teammate explanation
├── README.md                      # Project overview and reproduction steps
└── pyproject.toml                 # Python package metadata
```

## Final release command sequence

Do not run this section until the presentation/video links and repository details are
confirmed:

```powershell
git add .
git commit -m "Prepare Relay Samsung PRISM submission"
git remote add origin https://github.com/<GITHUB-HANDLE>/<REPOSITORY-NAME>.git
git push -u origin main
git tag -a v1.0.0-submission -m "Samsung PRISM hackathon submission"
git push origin v1.0.0-submission
```

Authentication should use GitHub's browser/device login, Git Credential Manager, or
an approved SSH key. Never paste a GitHub token or model API key into a tracked file.
