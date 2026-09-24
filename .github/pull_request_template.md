## What and why

<!-- What does this change, and what problem does it solve? Link any issue. -->

## How I checked it

<!-- Tick what applies; see CONTRIBUTING.md#verifying-a-change. -->

- [ ] `pytest` passes, with a test for new behaviour or a fixed bug
- [ ] Booted with `docker compose up` and got a real answer in the chat page
- [ ] Ran the live tests (`RUN_LIVE_TESTS=1 pytest -m live`)
- [ ] Followed the README's local steps from a fresh clone (setup changes)
- [ ] Deployed to Render (`render.yaml` changes; say what you saw)

## Checklist

- [ ] No credentials in the diff, including `.env` values in examples or logs
- [ ] README updated for anything a user sees, including new error messages
- [ ] CLAUDE.md updated for any quirk a maintainer would otherwise rediscover
- [ ] `requirements*.txt` regenerated from the `.in` files, if dependencies changed
