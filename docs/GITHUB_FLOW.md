# GitHub flow

The repository is private. Production is deployed automatically to the AWS
Lightsail instance only after all checks pass on `main`.

## Daily workflow

1. Create a branch from an updated `main`:

   ```bash
   git switch main
   git pull --ff-only
   git switch -c feature/short-description
   ```

2. Make and validate the change locally.
3. Commit and push the branch.
4. Open a pull request to `main`.
5. Merge only after `Sensitive files`, `Backend tests` and `Frontend build`
   pass.
6. A merge to `main` deploys the exact tested revision to production.

## Production deployment

The pipeline packages only Git-tracked files. On the server it preserves:

- `.env` and every API credential;
- `outputs/`, `output/` and `tmp/`;
- `c3po/data/` and Docker volumes;
- WhatsApp sessions and runtime state.

It then validates Docker Compose, rebuilds C3PO and checks both the local web
endpoint and the protected API endpoint. The deployed commit is recorded in
`.deploy-version` on the server.

## Manual release or rollback

Open **Actions > C3PO pipeline > Run workflow**, enter a commit SHA, tag or
branch in `ref`, and run it. The same tests execute before that revision can be
deployed. This is the rollback path as well: use the SHA of the last known-good
commit.

## Repository secrets

The deployment job expects these GitHub Actions secrets:

- `C3PO_AWS_HOST`
- `C3PO_AWS_USER`
- `C3PO_AWS_SSH_KEY`
- `C3PO_AWS_KNOWN_HOSTS`

The SSH credential is a dedicated deployment key. It is not the AWS account
password and must not be stored in the repository.

