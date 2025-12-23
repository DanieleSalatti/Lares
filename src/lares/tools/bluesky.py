"""BlueSky reading tools.

Wraps the bluesky_reader module for Letta tool usage.
"""

from lares.bluesky_reader import get_user_feed, search_posts


def read_bluesky_user(handle: str, limit: int = 5) -> str:
    """
    Read recent posts from a BlueSky user.

    Args:
        handle: The user's handle (e.g., "user.bsky.social" or just "username")
        limit: Maximum number of posts to return (default 5)

    Returns:
        Formatted string containing the user's recent posts
    """
    result = get_user_feed(handle, limit=limit)
    return result.format_summary(max_posts=limit)


def search_bluesky(query: str, limit: int = 10) -> str:
    """
    Search BlueSky posts.

    Args:
        query: Search query string
        limit: Maximum number of results (default 10)

    Returns:
        Formatted string containing matching posts
    """
    result = search_posts(query, limit=limit)
    return result.format_summary(max_posts=limit)


def post_to_bluesky(text: str) -> str:
    """
    Post a message to BlueSky.

    Args:
        text: The text to post (max 300 characters)

    Returns:
        Status message indicating success or failure
    """
    from lares.bluesky_reader import create_post

    result = create_post(text)
    return result.format_result()
