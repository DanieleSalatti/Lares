"""RSS feed reader tool for Lares.

Provides functionality to fetch and parse RSS/Atom feeds for research
and news monitoring purposes.
"""

from dataclasses import dataclass
from types import ModuleType
from typing import Any

import structlog

log = structlog.get_logger()

# Lazy import feedparser to avoid startup overhead
_feedparser: ModuleType | None = None


def _get_feedparser() -> ModuleType:
    """Lazy load feedparser module."""
    global _feedparser
    if _feedparser is None:
        try:
            import feedparser  # type: ignore[import-untyped]

            _feedparser = feedparser
        except ImportError:
            raise ImportError(
                "feedparser is required for RSS reading. "
                "Install it with: pip install feedparser"
            )
    return _feedparser


@dataclass
class FeedEntry:
    """A single entry from an RSS/Atom feed."""
    title: str
    link: str
    published: str | None
    summary: str | None
    author: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "link": self.link,
            "published": self.published,
            "summary": self.summary,
            "author": self.author,
        }

    def format_brief(self) -> str:
        """Format as a brief one-liner."""
        date_str = f" ({self.published})" if self.published else ""
        return f"• {self.title}{date_str}"

    def format_full(self) -> str:
        """Format with full details."""
        lines = [f"**{self.title}**"]
        if self.author:
            lines.append(f"  By: {self.author}")
        if self.published:
            lines.append(f"  Date: {self.published}")
        if self.summary:
            # Truncate long summaries
            summary = self.summary[:300] + "..." if len(self.summary) > 300 else self.summary
            # Remove HTML tags (basic)
            import re
            summary = re.sub(r'<[^>]+>', '', summary)
            lines.append(f"  {summary}")
        lines.append(f"  🔗 {self.link}")
        return "\n".join(lines)


@dataclass
class FeedResult:
    """Result of parsing an RSS feed."""
    feed_title: str
    feed_link: str
    entries: list[FeedEntry]
    error: str | None = None

    def format_summary(self, max_entries: int = 5) -> str:
        """Format feed as a readable summary."""
        if self.error:
            return f"❌ Error reading feed: {self.error}"

        lines = [f"📰 **{self.feed_title}**", f"   {self.feed_link}", ""]

        for entry in self.entries[:max_entries]:
            lines.append(entry.format_brief())

        remaining = len(self.entries) - max_entries
        if remaining > 0:
            lines.append(f"  ... and {remaining} more entries")

        return "\n".join(lines)


def read_feed(url: str, max_entries: int = 10) -> FeedResult:
    """
    Read and parse an RSS/Atom feed.

    Args:
        url: The URL of the RSS/Atom feed
        max_entries: Maximum number of entries to return (default 10)

    Returns:
        FeedResult containing feed metadata and entries
    """
    log.info("reading_rss_feed", url=url, max_entries=max_entries)

    try:
        feedparser = _get_feedparser()
        feed = feedparser.parse(url)

        # Check for parsing errors
        if feed.bozo and not feed.entries:
            error_msg = (
                str(feed.bozo_exception)
                if hasattr(feed, "bozo_exception")
                else "Unknown parsing error"
            )
            log.warning("rss_feed_error", url=url, error=error_msg)
            return FeedResult(
                feed_title="Unknown",
                feed_link=url,
                entries=[],
                error=error_msg
            )

        # Extract feed metadata
        feed_title = feed.feed.get('title', 'Untitled Feed')
        feed_link = feed.feed.get('link', url)

        # Parse entries
        entries = []
        for entry in feed.entries[:max_entries]:
            # Try to get published date in various formats
            published = None
            if hasattr(entry, 'published'):
                published = entry.published
            elif hasattr(entry, 'updated'):
                published = entry.updated

            # Get summary, falling back to content
            summary = None
            if hasattr(entry, 'summary'):
                summary = entry.summary
            elif hasattr(entry, 'content') and entry.content:
                summary = entry.content[0].get('value', '')

            entries.append(FeedEntry(
                title=entry.get('title', 'Untitled'),
                link=entry.get('link', ''),
                published=published,
                summary=summary,
                author=entry.get('author'),
            ))

        log.info("rss_feed_parsed",
                url=url,
                feed_title=feed_title,
                entry_count=len(entries))

        return FeedResult(
            feed_title=feed_title,
            feed_link=feed_link,
            entries=entries
        )

    except ImportError as e:
        log.error("rss_dependency_missing", error=str(e))
        return FeedResult(
            feed_title="Unknown",
            feed_link=url,
            entries=[],
            error=str(e)
        )
    except Exception as e:
        log.error("rss_feed_error", url=url, error=str(e), error_type=type(e).__name__)
        return FeedResult(
            feed_title="Unknown",
            feed_link=url,
            entries=[],
            error=str(e)
        )


def read_multiple_feeds(urls: list[str], max_entries_per_feed: int = 5) -> list[FeedResult]:
    """
    Read multiple RSS feeds.

    Args:
        urls: List of feed URLs to read
        max_entries_per_feed: Maximum entries per feed

    Returns:
        List of FeedResult objects
    """
    log.info("reading_multiple_feeds", feed_count=len(urls))

    results = []
    for url in urls:
        result = read_feed(url, max_entries=max_entries_per_feed)
        results.append(result)

    return results


# Convenience function for quick testing
if __name__ == "__main__":
    # Test with a well-known feed
    result = read_feed("https://hnrss.org/frontpage", max_entries=5)
    print(result.format_summary())
