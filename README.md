# white-rabbit

*Follow the white rabbit.* white-rabbit shows, in the Claude Code statusline, what the
current session left behind:

- **MR:** the GitLab merge requests the session opened, with their state;
- **Next:** the actions the session expects from you, the next one first;
- **Notes:** the note files the session wrote (optional).

It also asks Claude to end every answer with a short recap block (what was done, merge
requests, next action), consistent with the statusline.

Pure Python (3.10+), no dependency, no network except `glab api` to refresh merge requests.

## Install

The repository is private: ask for access first; git must be able to clone it (HTTPS credentials or SSH key).

Requirements: Python 3.10+ and `pipx`; `glab` installed and logged in, or merge requests are
captured but their state (opened, merged) is never refreshed.

    pipx install git+https://github.com/r3n0j/white-rabbit@v0.2.0
    white-rabbit setup --dry-run   # shows what it will add to ~/.claude/settings.json
    white-rabbit setup

`setup` adds the statusline and three hooks (PostToolUse on Bash/Write/Edit, Stop, SessionStart)
with the absolute path of the command, keeps a `settings.json.bak`, and never replaces an
existing statusline without `--force`.

Then open a **new** Claude Code session (the instructions are given at session start): the
statusline shows the merge requests and the Next line, and answers end with the recap block.

### Upgrade

The install is pinned to a tag, so `pipx upgrade` does not move to a newer one: install the new
tag over the old one (the hooks keep working, no new `setup` needed).

    pipx install --force git+https://github.com/r3n0j/white-rabbit@v<new version>

## How it works

- A merge request URL printed by a Bash command becomes a merge request of the session only
  when a part of the command (split on `&&`, `||`, `;`, `|`) pushes or creates one:
  `git push`, `git pushon`, `glab mr create` (`gitlab.capture_commands`; `git -C repo push`
  and `cd repo && git push … | tail -5` count). Reading a file or a transcript that quotes a
  merge request never captures it; `white-rabbit add-mr <url>` adds one by hand.
- The to-do list is written by Claude itself with `white-rabbit todo "[next] …" "…"`: the
  SessionStart hook gives it the instructions (see `white-rabbit instructions`).
- The same hook asks Claude to end every answer with a recap block: Done (with the merge
  requests, branches and commits of the answer, and the notes it wrote when notes are on),
  Step and Next, the Next line being the `[next]` action of the to-do list. Turn it off
  with `"recap": {"enabled": false}`.
- One JSON file per session in `~/.claude/white-rabbit/`, purged after 30 days.

## Settings

Optional `~/.config/white-rabbit/config.json` (defaults shown):

    {
      "data_dir": "~/.claude/white-rabbit",
      "gitlab": {"enabled": true, "hosts": ["gitlab.com"],
                 "capture_commands": ["git push", "git pushon", "glab mr create"],
                 "glab": "glab"},
      "notes": {"enabled": false, "root": "~/notes", "link": "file", "vault": "", "extensions": [".md"]},
      "todo": {"instructions": true},
      "recap": {"enabled": true}
    }

`notes.link` is `obsidian` (`obsidian://open?vault=<vault>&file=…`), `file` or `none`.
A wrong value keeps its default and is logged in `<data_dir>/errors.log`.
`gitlab.ignore_commands` (before 0.3) is no longer read: list the commands that push or create
a merge request in `capture_commands` instead.

## Commands

    white-rabbit hook capture|refresh|start
    white-rabbit todo ["[next] action" ...]
    white-rabbit statusline
    white-rabbit add-mr <url> [session]
    white-rabbit instructions
    white-rabbit setup [--dry-run] [--force]

`rabbit` is a short alias.
