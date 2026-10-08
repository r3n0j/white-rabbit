"""Adaptateur GitLab : une URL de MR dans la sortie d'une commande est une MR de la
session, sauf pour les lectures connues ; l'état vient de `glab api`."""
import json
import re
import subprocess
import urllib.parse

FIELDS = ("state", "title", "source_branch", "target_branch")


class GitLab:
    def __init__(self, settings):
        hosts = "|".join(re.escape(h) for h in settings["hosts"]) or r"(?!)"
        self.url = re.compile(r"https://(%s)/([\w.\-/]+?)/-/merge_requests/(\d+)(?![\w/])" % hosts)
        self.reads = [re.compile(r"\b" + r"\s+".join(map(re.escape, cmd.split())) + r"\b")
                      for cmd in settings["ignore_commands"] if cmd.split()]
        self.glab = settings["glab"]

    def mr_urls(self, command, output):
        """URL de MR distinctes de `output`, dans l'ordre ; [] si `command` est une lecture."""
        if any(read.search(command or "") for read in self.reads):
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
