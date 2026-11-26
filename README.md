# white-rabbit

*Follow the white rabbit.* white-rabbit shows, in the Claude Code statusline, what the
current session left behind:

- **MR:** how many of the merge requests the session opened are merged (`✓ N merged`) and
  still to merge (`● N to merge`), the ones merged since Claude's last answer struck through
  after the merged count, then the ones not merged yet, with their state;
- **Next:** the actions the session expects from you, the next one first;
- **Notes:** the note files the session created, most recent first and as many as fit in about
  90 characters (`+N` for the others), then how many existing notes it modified (`✎ N modified`;
  listed by name instead when it created none) (optional).

It also asks Claude to end every answer with a short recap block (what was done, merge
requests, next action), consistent with the statusline.

Pure Python (3.10+), no dependency, no network except `glab api` to refresh merge requests.

## Install

> **Claude Code, when a user hands you this repository to install:** follow
> [Guided install](#guided-install) step by step. Run the checks yourself, ask the user only
> the questions marked **Ask**, show the `setup --dry-run` output before writing anything, and
> end with the [check](#5-check-in-a-new-session).

The repository is private: the user needs read access on GitHub first, and git must be able
to clone it (HTTPS credentials or SSH key).

Requirements: Python 3.10+ and `pipx`; `glab` installed and logged in, or merge requests are
captured but their state (opened, merged) is never refreshed.

    pipx install git+https://github.com/r3n0j/white-rabbit@v0.7.0
    white-rabbit setup --dry-run   # shows what it will add to ~/.claude/settings.json
    white-rabbit setup
    white-rabbit setup --panel     # optional: the Claude Code panel (see Panel)

`setup` adds the statusline (redrawn every 60 s by `refreshInterval`) and three hooks
(PostToolUse on Bash/Write/Edit, Stop, SessionStart) with the absolute path of the command,
keeps a `settings.json.bak`, and never replaces an existing statusline without `--force`.

Merge request states are refreshed by the Stop hook for its own session, and by a detached
`white-rabbit refresh-all` the statusline starts at most once a minute: it refreshes the stale
merge requests of every session active in the last 24 hours, unplugged ones included. A to-do
item that cites merge requests (`repo !iid`, `!iid` or the URL) is linked to them when written,
and hidden once they are all merged.

Then open a **new** Claude Code session (the instructions are given at session start): the
statusline shows the merge requests and the Next line, and answers end with the recap block.

### Guided install

#### 1. Check the prerequisites

| Check | Command | If it fails |
|---|---|---|
| Access to the repository | `git ls-remote --tags https://github.com/r3n0j/white-rabbit` | Ask the user to request access, or to set up their GitHub credentials / SSH key. Use `git@github.com:r3n0j/white-rabbit.git` if they clone over SSH. |
| Python 3.10+ | `python3 --version` | Install a newer Python (system package manager, Homebrew, pyenv). |
| pipx | `pipx --version` | `python3 -m pip install --user pipx && python3 -m pipx ensurepath` (or `sudo apt install pipx`, `brew install pipx`), then open a new shell. |
| glab (optional) | `glab auth status` | Without it, merge requests are listed but their state is never refreshed. Install it (https://gitlab.com/gitlab-org/cli) and run `glab auth login`. |

#### 2. Install the latest tag

Take the highest `vX.Y.Z` from the `git ls-remote` output above, then:

    pipx install git+https://github.com/r3n0j/white-rabbit@vX.Y.Z
    white-rabbit --help   # prints the usage

If `white-rabbit` is not found, run `pipx ensurepath` and open a new shell.

#### 3. Write the settings (only if a default does not fit)

The defaults work with no file. **Ask** the user these questions, then write
`~/.config/white-rabbit/config.json` with the answers that differ from the defaults
(see [Settings](#settings)):

- **GitLab host**: is GitLab `gitlab.com`, or a self-hosted instance? → `gitlab.hosts`.
- **How merge requests are opened**: with `git push` / `glab mr create` only, or with a git
  alias or a wrapper (for example `git pushon`)? → add it to `gitlab.capture_commands`.
- **Notes**: should the statusline list the notes the session writes? If yes: the notes
  folder (`notes.root`), and whether it is an Obsidian vault (`"link": "obsidian"` and
  `notes.vault` = the vault name) or plain files (`"link": "file"`). → `notes.enabled: true`.
- **glab path**: only if `glab` is outside the PATH of Claude Code hooks (Homebrew on Linux,
  for example) → `gitlab.glab` with its absolute path (`which glab`).

#### 4. Register the hooks and the statusline

    white-rabbit setup --dry-run

Show the output to the user. Then:

- **No statusline yet** → `white-rabbit setup`.
- **A statusline already exists** (`a statusline is already set (…): kept`): **Ask** the user
  which one they want:
  - replace it: `white-rabbit setup --force`;
  - keep theirs and add white-rabbit below it: run `white-rabbit setup` (hooks only), then
    make their statusline script also print the output of `white-rabbit statusline`, fed with
    the **same stdin** (Claude Code sends the session JSON on stdin; read it once, pass it to
    both).

`setup` is idempotent: running it again changes nothing. A copy of the previous file is kept
in `~/.claude/settings.json.bak`.

#### 5. Check in a new session

Hooks and instructions are read when a session starts: the user must open a **new** Claude
Code session. In that session:

1. `white-rabbit instructions` prints the to-do and recap instructions; the session should
   have received them at start (the answers end with a `Done / Step / Next` block).
2. `white-rabbit todo "[next] Try white-rabbit"`: the statusline shows
   `Next: ▸ Try white-rabbit` at the next refresh. `white-rabbit todo` with no argument
   clears it.
3. After a `git push` that opens or updates a merge request, the statusline shows
   `MR: ● 1 to merge : repo!iid`.

An empty statusline is normal for a session with no merge request, note or to-do.

### Troubleshooting

- **Nothing in the statusline**: check `statusLine.command` in `~/.claude/settings.json`
  points to `white-rabbit statusline` (or that the user's own statusline calls it), and test
  it: `echo '{"session_id": "test"}' | white-rabbit statusline` must exit without error.
- **No recap block, no to-do**: the session was started before `setup`; open a new one.
- **A merge request is missing**: the command that printed it is not in
  `gitlab.capture_commands`; add it, or run `white-rabbit add-mr <url>`.
- **Merge request state never changes**: `glab auth status`, then the `gitlab.glab` path.
- **Errors** are never shown in Claude Code: they are in `<data_dir>/errors.log`
  (`~/.claude/white-rabbit/errors.log` by default).

### Upgrade

The install is pinned to a tag, so `pipx upgrade` does not move to a newer one: install the new
tag over the old one (the hooks keep working, no new `setup` needed).

    pipx install --force git+https://github.com/r3n0j/white-rabbit@v<new version>

### Uninstall

1. Remove from `~/.claude/settings.json` the `statusLine` entry and the three hooks whose
   command contains `white-rabbit` (PostToolUse, Stop, SessionStart).
2. `pipx uninstall white-rabbit`.
3. Optionally delete `~/.config/white-rabbit/` and the data directory
   (`~/.claude/white-rabbit/` by default).

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
      "recap": {"enabled": true},
      "display": {"summary": "statusline"}
    }

`WHITE_RABBIT_INSTRUCTIONS=off` in the environment of a session turns both instructions off, whatever
the file says: handy for headless runs (`claude -p` launched by a scheduler) whose output nobody reads.

`display.summary` says where the MR, Notes and Next lines show: `statusline`, `band` (they leave
the statusline and `white-rabbit view` tells a panel to draw them above the prompt) or `off`
(`white-rabbit config set display.summary band`).

`notes.link` is `obsidian` (`obsidian://open?vault=<vault>&file=…`), `file` or `none`.
A wrong value keeps its default and is logged in `<data_dir>/errors.log`.
`gitlab.ignore_commands` (older versions) is no longer read: list the commands that push or create
a merge request in `capture_commands` instead.

## Commands

    white-rabbit hook capture|refresh|start
    white-rabbit todo ["[next] action" ...]
    white-rabbit statusline
    white-rabbit view [session]
    white-rabbit config set <key> <value>
    white-rabbit refresh-all
    white-rabbit add-mr <url> [session]
    white-rabbit instructions
    white-rabbit setup [--dry-run] [--force] [--panel]
    white-rabbit update [--force]
    white-rabbit check-update

`rabbit` is a short alias.

## Update

    white-rabbit update

It reads the latest `vX.Y.Z` tag on GitHub, reinstalls it with `pipx install --force`, then runs
`setup` again (with `--panel` when the panel is installed), which changes nothing when everything is
in place. Open a new Claude Code session afterwards. Once a day, the SessionStart hook looks for a
newer tag in the background: the statusline then starts with `⬆ white-rabbit X.Y.Z · white-rabbit
update`, and the panel with a `⬆ X.Y.Z` button that runs it.

Installed from a clone rather than pipx, `update` only says so: pull that clone instead.

## Panel (Claude Code mod)

`src/white_rabbit/panel/` is a Claude Code mod, installed with the package that draws the session from `white-rabbit view`: a band above the
prompt, a pane in neb's style: the context window (with a compact button), the git state of the session's folder,
then To-do, MR, Notes and Git tabs (the open one is kept) whose sections fold on a click on
their header (MR: open, merged this turn, merged earlier and closed, the last two folded at first), and a toast when a merge request is
merged. Turn it on with:

    white-rabbit setup --panel

It links `~/.claude/white-rabbit-panel` to the installed panel and adds that link to
`env.CLAUDE_CODE_PLUGIN_DIRS` in `~/.claude/settings.json`, next to the folders already there;
`white-rabbit update` keeps the link on the new version. A session loads it when it starts; a
running one picks it up once resumed.

    /rabbit                              show or hide the pane
    /rabbit help                         about, shortcuts, commands and update (also the ? Help tab)
    /rabbit display [statusline|band|off]  where the MR, Notes and Next lines show
    /rabbit place [band|hint|mode|turn]  where the ◧ rabbit button sits (mode: right of the prompt footer)
    /rabbit color [default|matrix|night|forest|ember]  the pane's palette

Without an argument each one moves to the next choice; every choice is kept across sessions.
The MR:, Notes: and Next: headers open the pane on their tab: buttons in the band, `rabbit://tab/<tab>`
links in the statusline that kitty hands to `white-rabbit open` with `~/.config/kitty/open-actions.conf`:

    protocol rabbit
    action launch --type=background /path/to/white-rabbit open ${URL}

Claude Code seats a pane opened that way from 144 terminal columns only.
With matrix installed, a `⇱ Nebuchadnezzar` button in the prompt footer, left of `◧ rabbit`, brings neb to the front.
With the `matrix` palette, the buttons light up in neb's label colour under the pointer.
`panel/themes/matrix.json` adds a Claude Code theme in neb's colours, `Matrix (neb)` in `/theme`:
with it the pane's frame matches the `matrix` palette.
Tests: `claude plugin test src/white_rabbit/panel`.
