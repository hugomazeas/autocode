import re
import httpx
from .base import RepoPlatform


class GitHubPlatform(RepoPlatform):
    def __init__(self, token: str):
        self.token = token

    def _parse_repo(self, repo_url: str) -> tuple[str, str]:
        """Extract owner/repo from git URL."""
        # Handle SSH: git@github.com:owner/repo.git
        m = re.search(r"github\.com[:/](.+?)/(.+?)(?:\.git)?$", repo_url)
        if not m:
            raise ValueError(f"Cannot parse GitHub repo from: {repo_url}")
        return m.group(1), m.group(2)

    async def create_pr(
        self,
        repo_url: str,
        branch: str,
        base_branch: str,
        title: str,
        body: str,
    ) -> str:
        owner, repo = self._parse_repo(repo_url)
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"https://api.github.com/repos/{owner}/{repo}/pulls",
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/vnd.github+json",
                },
                json={
                    "title": title,
                    "body": body,
                    "head": branch,
                    "base": base_branch,
                },
            )
            resp.raise_for_status()
            return resp.json()["html_url"]
