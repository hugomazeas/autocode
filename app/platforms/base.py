from abc import ABC, abstractmethod


class RepoPlatform(ABC):
    @abstractmethod
    async def create_pr(
        self,
        repo_url: str,
        branch: str,
        base_branch: str,
        title: str,
        body: str,
    ) -> str:
        """Create a PR/MR and return its URL."""
        pass
