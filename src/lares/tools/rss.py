"""RSS feed reading tools.

Wraps the rss_reader module for Letta tool usage.
"""

from lares.rss_reader import read_feed, read_multiple_feeds


def read_rss_feed(url: str, max_entries: int = 5) -> str:
    """
    Read and parse an RSS or Atom feed from the given URL.

    Args:
        url: The URL of the RSS/Atom feed to read
        max_entries: Maximum number of entries to return (default 5)

    Returns:
        Formatted string containing feed entries with titles, dates, and summaries
    """
    result = read_feed(url, max_entries=max_entries)
    return result.format_summary(max_entries=max_entries)


def read_rss_feeds(feed_urls: list[str], max_entries_per_feed: int = 3) -> str:
    """
    Read multiple RSS/Atom feeds and combine the results.

    Args:
        feed_urls: List of feed URLs to read
        max_entries_per_feed: Maximum entries per feed (default 3)

    Returns:
        Combined formatted string with entries from all feeds
    """
    results = read_multiple_feeds(feed_urls, max_entries_per_feed=max_entries_per_feed)
    formatted = [result.format_summary(max_entries=max_entries_per_feed) for result in results]
    return "\n\n".join(formatted)
