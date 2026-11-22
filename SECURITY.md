# Security Policy

## Supported versions

Only the latest release receives fixes.

## Reporting a vulnerability

Please do not open a public issue. Use GitHub's **Report a vulnerability** button under the
repository's Security tab (private advisory). Expect an acknowledgement within a few days.

## Notes for users

- Reports are written as static files; HTML output escapes all content.
- The optional LLM backends send finding text (never raw tables) to the endpoint you configure.
  API keys are read from environment variables only and are never written to disk.
- Backend URLs must use http or https.
- XES files are parsed with `defusedxml`, which rejects entity-expansion attacks.
