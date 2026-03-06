import re
import urllib.parse
import httpx
from .base import RepoPlatform


class GitLabPlatform(RepoPlatform):
    def __init__(self, token: str):
        self.token = token

    def _parse_project(self, repo_url: str) -> str:
        """Extract URL-encoded project path from git URL."""
        m = re.search(r"gitlab\.com[:/](.+?)(?:\.git)?$", repo_url)
        if not m:
            raise ValueError(f"Cannot parse GitLab project from: {repo_url}")
        return urllib.parse.quote(m.group(1), safe="")

    async def create_pr(
        self,
        repo_url: str,
        branch: str,
        base_branch: str,
        title: str,
        body: str,
    ) -> str:
        project = self._parse_project(repo_url)
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"https://gitlab.com/api/v4/projects/{project}/merge_requests",
                headers={"PRIVATE-TOKEN": self.token},
                json={
                    "title": title,
                    "description": body,
                    "source_branch": branch,
                    "target_branch": base_branch,
                },
            )
            resp.raise_for_status()
            return resp.json()["web_url"]
