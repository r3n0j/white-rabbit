"""Adaptateur GitLab : une URL de MR dans la sortie d'une commande qui pousse ou crée une MR
(`git push`, `glab mr create`…) est une MR de la session ; l'état vient de `glab api`."""
import json
import re
import subprocess
import urllib.parse

FIELDS = ("state", "title", "source_branch", "target_branch")
SEGMENTS = re.compile(r"&&|\|\||[;|\n]")
ASSIGNMENT = re.compile(r"^\w+=")
GIT_OPTIONS_WITH_VALUE = ("-C", "-c")


def _words(segment):
    """Mots d'un segment sans les affectations de tête, le chemin du programme (`/usr/bin/git`)
    ni les options globales de git (`git -C repo push` → `git push`)."""
    words = segment.split()
    while words and ASSIGNMENT.match(words[0]):
        words = words[1:]
    if not words:
        return []
    words = [words[0].rsplit("/", 1)[-1]] + words[1:]
    if words[0] == "git":
        rest = words[1:]
        while rest and rest[0] in GIT_OPTIONS_WITH_VALUE:
            rest = rest[2:]
        words = ["git"] + rest
    return words


class GitLab:
    def __init__(self, settings):
        hosts = "|".join(re.escape(h) for h in settings["hosts"]) or r"(?!)"
        self.url = re.compile(r"https://(%s)/([\w.\-/]+?)/-/merge_requests/(\d+)(?![\w/])" % hosts)
        self.writers = [cmd.split() for cmd in settings["capture_commands"] if cmd.split()]
        self.glab = settings["glab"]

    def _is_writer(self, command):
        """Vrai si un segment de la commande (séparés par &&, ||, ;, |) commence par une commande
        de `capture_commands` : lire un transcript ou un fichier qui cite une MR ne la capture pas."""
        return any(_words(segment)[:len(writer)] == writer
                   for segment in SEGMENTS.split(command or "") for writer in self.writers)

    def mr_urls(self, command, output):
        """URL de MR distinctes de `output`, dans l'ordre ; [] si `command` ne pousse ni ne crée de MR."""
        if not self._is_writer(command):
            return []
        urls = []
        for host, project, iid in self.url.findall(output or ""):
            url = "https://%s/%s/-/merge_requests/%s" % (host, project, iid)
            if url not in urls:
                urls.append(url)
        return urls

    def parse(self, url):
        match = self.url.fullmatch(url or "")
        return (match.group(2), int(match.group(3))) if match else None

    def fetch_state(self, url, timeout):
        match = self.url.fullmatch(url)
        host, project, iid = match.group(1), match.group(2), match.group(3)
        endpoint = "projects/%s/merge_requests/%s" % (urllib.parse.quote(project, safe=""), iid)
        command = [self.glab, "api", endpoint] + ([] if host == "gitlab.com" else ["--hostname", host])
        out = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=True)
        body = json.loads(out.stdout)
        return {key: body.get(key) for key in FIELDS}
