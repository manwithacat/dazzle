Monitor CI/CD pipeline status for the current branch. Follow these steps:

## 1. Find the latest run

- Run `gh run list --branch $(git branch --show-current) --limit 3 --json status,conclusion,name,url,databaseId` to find active runs.

## 2. Poll until complete

- For each `in_progress` or `queued` run, poll using `gh run view <run-id> --json status,conclusion,name` every 15 seconds, up to 20 attempts.
- Show a brief status update each poll.

## 3. Report result

- If the run concludes with `success`, report success and the run URL.
- If the run concludes with `failure`, fetch the failed job logs with `gh run view <run-id> --log-failed | tail -80` and report the failure details so the user can decide what to do.
- If no CI run is found, note that no workflow is running and stop.
