"""Consigne injectée au SessionStart (cf. `white-rabbit instructions`) : ToDo et récap de fin
de réponse, chacun activable dans la configuration."""
import json
import os

TODO = """\
white-rabbit keeps this session's to-do list in the Claude Code statusline.
Whenever the list of actions expected from the user changes (an action is added, done,
dropped, or the next one changes), run:
  white-rabbit todo "[next] <the very next action>" "<another action>" ...
- one action per argument, the complete list on every call (it replaces the previous one);
- exactly one action prefixed with [next];
- concrete user actions only, never what you plan to do yourself; at most 10;
- run `white-rabbit todo` without arguments when nothing is expected from the user."""

RECAP_HEAD = """\
End every answer, a plain answer to a question included, with this block:

```
---
> ✅ **Done** : <what this answer did, in a few words>
> ↳ 🔗 **MR** : <full url> (!<iid>)
> ↳ 🌿 **Branch** : <source> → <target>
> ↳ 📝 **Commit(s)** : <type(scope): description>[, …]{note_template}
> 📍 **Step** : <where the work of this conversation stands>
> 👉 **Next** : <the next concrete action expected from the user>
```

A subagent never adds this block to its report: the main agent talks to the user.

Done
- Only when the answer had an effect: file created or changed, command with a side effect,
  commit, push, merge request, message sent. Reading or searching alone does not count: drop the line.
- One very short line: the result, not the list of steps.
- The block only covers what this answer delivered; the statusline already shows the whole
  session. Never query a forge or any service to build it.

Delivery sub-lines
- Only when the answer made commits or merge requests, under Done.
- Prefixed with `↳ `, never a `- ` bullet: a Markdown list would swallow the Step and Next
  lines that follow it.
- MR: always the full URL, then the number. Several merge requests: repeat the MR / Branch /
  Commit(s) trio for each one, none left out. A commit without a merge request: only Commit(s)."""

NOTE = """

Note sub-line
- Only when a note was created or changed during the answer, under Done, with the same `↳ ` prefix.
- A clickable Markdown link to the note, its title as text: {link}.
- One sub-line per note."""

RECAP_TAIL = """

Step
- Take it from the plan of the conversation (numbered steps, choice already made); failing
  that, from where the user tracks the work (notes, plan, spec); failing that, from the git
  branch and the task asked. Name it with the plan's words, then its state (done, in progress,
  blocked on …).
- One piece of work only: the one of this conversation, never another picked from a list.
- No piece of work (isolated question, discussion): `**Step** : no ongoing work, <topic>`.
  Never make one up.

Next
- One action, concrete and doable right away: approve, choose, test, provide a key, review a
  merge request… Several options still open: name them in one line.
- Nothing expected from the user: say so ("Next: nothing, I keep going on …").{todo_link}

Order and form
- The body of the answer, then the block, always the last lines of the text; a tool call that
  asks the user a question comes after the text, so after the block.
- A `---` separator, then lines quoted with `>`, no title. Keep the emojis and the exact labels
  right after them (`**Done**`, `**Step**`, `**Next**`, `**MR**`, `**Branch**`,
  `**Commit(s)**`{note_label}) so a tool can find them.
- Labels stay in English; the content follows the language of the conversation."""

TODO_LINK = """
- When the to-do list changes, call `white-rabbit todo` before writing the block; the Next
  line is the same action as the `[next]` one of the to-do list."""


def _note_link(notes):
    if not notes["enabled"] or notes["link"] == "none":
        return None
    root = os.path.realpath(notes["root"])
    if notes["link"] == "obsidian":
        vault = notes["vault"] or os.path.basename(root)
        return ("`obsidian://open?vault=%s&file=<path relative to %s, without extension, "
                "URL-encoded>`" % (vault, root))
    return "`file://<absolute path of the note under %s, URL-encoded>`" % root


def _recap(cfg):
    link = _note_link(cfg["notes"])
    template = "\n> ↳ 📓 **Note** : [<note title>](<link>)" if link else ""
    text = RECAP_HEAD.replace("{note_template}", template)
    if link:
        text += NOTE.replace("{link}", link)
    tail = RECAP_TAIL.replace("{todo_link}", TODO_LINK if cfg["todo"]["instructions"] else "")
    return text + tail.replace("{note_label}", ", `**Note**`" if link else "")


def render(cfg):
    """Consigne effective selon les réglages ; chaîne vide si ToDo et récap sont désactivés."""
    parts = []
    if cfg["todo"]["instructions"]:
        parts.append(TODO)
    if cfg["recap"]["enabled"]:
        parts.append(_recap(cfg))
    return "\n\n".join(parts)


def session_start_output(cfg):
    """Sortie JSON du hook SessionStart, ou None s'il n'y a rien à injecter."""
    text = render(cfg)
    if not text:
        return None
    return json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}})
