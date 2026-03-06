import re
import httpx
from .base import RepoPlatform


class BitbucketPlatform(RepoPlatform):
    def __init__(self, token: str):
        self.token = token

    def _parse_repo(self, repo_url: str) -> tuple[str, str]:
        m = re.search(r"bitbucket\.org[:/](.+?)/(.+?)(?:\.git)?$", repo_url)
        if not m:
            raise ValueError(f"Cannot parse Bitbucket repo from: {repo_url}")
        return m.group(1), m.group(2)

    async def create_pr(
        self,
        repo_url: str,
        branch: str,
        base_branch: str,
        title: str,
        body: str,
    ) -> str:
        workspace, repo_slug = self._parse_repo(repo_url)
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"https://api.bitbucket.org/2.0/repositories/{workspace}/{repo_slug}/pullrequests",
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                },
                json={
                    "title": title,
                    "description": body,
                    "source": {"branch": {"name": branch}},
                    "destination": {"branch": {"name": base_branch}},
                },
            )
            resp.raise_for_status()
            return resp.json()["links"]["html"]["href"]
