# Legacy single-file server

`app_single_file.py` is the original Dictate API: one file holding the model,
the endpoints, the cleanup rules, and a vocabulary-aware prompt builder. It has
been replaced by the `app/` package (`app.main:app`), which is what the systemd
unit and the deployment guide run.

It is kept here for two reasons:

- it is the reference for the vocabulary-boosting cleanup prompt, which the
  package version does not implement yet
- some installs may still be running it

Nothing else in the repository imports it. If you are deploying fresh, use
`app/`, not this.
