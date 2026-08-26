from datetime import datetime, timezone

from app.modules.news.domain.models import FeedItem, FeedItemType, Topic


DEFAULT_TOPICS = (
    Topic(
        id="diffractive-neural-networks",
        name="Diffractive Neural Networks",
        keywords=(
            "diffractive neural network",
            "diffractive deep neural network",
            "diffractive deep network",
            "diffractive optical neural network",
            "D2NN",
        ),
        negative_keywords=("job posting", "smart grid", "electric vehicle"),
        enabled_sources=("demo", "openalex"),
    ),
    Topic(
        id="optical-computing",
        name="Optical Computing",
        keywords=("optical computing",),
        enabled_sources=("openalex",),
    ),
    Topic(
        id="metasurface",
        name="Metasurface",
        keywords=("metasurface",),
        enabled_sources=("openalex",),
    ),
)

DEMO_TOPICS = (
    Topic(
        id="optical-ml",
        name="Optical ML",
        keywords=("optical", "diffractive"),
        negative_keywords=("job posting",),
        enabled_sources=("demo", "openalex"),
    ),
    Topic(
        id="research-tools",
        name="Research Tools",
        keywords=("research", "repository", "skill", "literature"),
        enabled_sources=("demo", "openalex"),
    ),
)


class DemoNewsProvider:
    """A deterministic local provider that exercises every Feed item type."""

    name = "demo"
    item_types = tuple(FeedItemType)
    uses_topics = True

    def fetch_items(self, *, topics: tuple[Topic, ...]) -> tuple[FeedItem, ...]:
        del topics
        fetched_at = datetime.now(timezone.utc).isoformat()
        return (
            FeedItem(
                id="demo:paper:diffractive-learning",
                type=FeedItemType.PAPER,
                source=self.name,
                title="Diffractive learning systems — demo paper",
                summary="A placeholder paper item for validating the optical research feed.",
                url="https://example.com/news/demo-paper",
                authors=("Demo Researcher",),
                published_at="2026-08-20T09:00:00+00:00",
                fetched_at=fetched_at,
                metadata={"venue": "Demo Proceedings"},
            ),
            FeedItem(
                id="demo:github-repo:research-workbench",
                type=FeedItemType.GITHUB_REPO,
                source=self.name,
                title="Research Workbench — demo repository",
                summary="A placeholder GitHub repository for research workflow tooling.",
                url="https://example.com/news/demo-repository",
                published_at="2026-08-19T09:00:00+00:00",
                fetched_at=fetched_at,
                metadata={"language": "TypeScript", "stars": 128},
            ),
            FeedItem(
                id="demo:github-skill:literature-review",
                type=FeedItemType.GITHUB_SKILL,
                source=self.name,
                title="Literature review — demo skill",
                summary="A placeholder skill for a structured research workflow.",
                url="https://example.com/news/demo-skill",
                published_at="2026-08-18T09:00:00+00:00",
                fetched_at=fetched_at,
                metadata={"repository": "demo/research-skills"},
            ),
            FeedItem(
                id="demo:ai-news:research-tools",
                type=FeedItemType.AI_NEWS,
                source=self.name,
                title="AI research tools — demo news",
                summary="A placeholder update used to validate a normalized AI News card.",
                url="https://example.com/news/demo-ai-news",
                published_at="2026-08-17T09:00:00+00:00",
                fetched_at=fetched_at,
                metadata={"publisher": "Demo Newsroom"},
            ),
            FeedItem(
                id="demo:x-post:optical-computing",
                type=FeedItemType.X_POST,
                source=self.name,
                title="Optical computing discussion — demo post",
                summary="A placeholder X post for testing the external discovery feed.",
                url="https://example.com/news/demo-x-post",
                authors=("Demo Account",),
                published_at="2026-08-16T09:00:00+00:00",
                fetched_at=fetched_at,
                metadata={"handle": "@demo"},
            ),
        )
