# white-rabbit

*Follow the white rabbit.* white-rabbit shows, in the Claude Code statusline, what the
current session left behind:

- **MR:** the GitLab merge requests the session opened, with their state;
- **ToDo:** the actions the session expects from you, the next one first;
- **Notes:** the note files the session wrote (optional).

Pure Python (3.10+), no dependency, no network except `glab api` to refresh merge requests.

## Install

    pipx install git+https://github.com/<account>/white-rabbit@v0.1.0
    white-rabbit setup --dry-run   # shows what it will add to ~/.claude/settings.json
    white-rabbit setup

`setup` adds the statusline and three hooks (PostToolUse on Bash/Write/Edit, Stop, SessionStart)
with the absolute path of the command, keeps a `settings.json.bak`, and never replaces an
existing statusline without `--force`.

## How it works

- A merge request URL printed by any Bash command becomes a merge request of the session,
  except for read commands (`glab mr list|view|diff`, `glab api`).
- The to-do list is written by Claude itself with `white-rabbit todo "[next] …" "…"`: the
  SessionStart hook gives it the instructions (see `white-rabbit instructions`).
- One JSON file per session in `~/.claude/white-rabbit/`, purged after 30 days.

## Settings

Optional `~/.config/white-rabbit/config.json` (defaults shown):

    {
      "data_dir": "~/.claude/white-rabbit",
      "gitlab": {"enabled": true, "hosts": ["gitlab.com"],
                 "ignore_commands": ["glab mr list", "glab mr view", "glab mr diff", "glab api"],
                 "glab": "glab"},
      "notes": {"enabled": false, "root": "~/notes", "link": "file", "vault": "", "extensions": [".md"]},
      "todo": {"instructions": true}
    }

`notes.link` is `obsidian` (`obsidian://open?vault=<vault>&file=…`), `file` or `none`.
A wrong value keeps its default and is logged in `<data_dir>/errors.log`.

## Commands

    white-rabbit hook capture|refresh|start
    white-rabbit todo ["[next] action" ...]
    white-rabbit statusline
    white-rabbit add-mr <url> [session]
    white-rabbit instructions
    white-rabbit setup [--dry-run] [--force]

`rabbit` is a short alias.
