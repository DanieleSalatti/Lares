"""Tests for the response parser module."""


from lares.response_parser import DiscordAction, parse_response


class TestParseResponse:
    """Tests for parse_response function."""

    def test_empty_text_returns_empty_list(self):
        """Empty or None input returns empty action list."""
        assert parse_response(None) == []
        assert parse_response("") == []
        assert parse_response("   ") == []

    def test_plain_text_becomes_reply(self):
        """Plain text is treated as a reply action."""
        actions = parse_response("Hello, world!")
        assert len(actions) == 1
        assert actions[0].type == "reply"
        assert actions[0].content == "Hello, world!"

    def test_silent_marker(self):
        """[silent] marker produces silent action."""
        actions = parse_response("[silent]")
        assert len(actions) == 1
        assert actions[0].type == "silent"

        # Case insensitive
        actions = parse_response("[SILENT] some thoughts")
        assert actions[0].type == "silent"

    def test_thinking_marker(self):
        """[thinking] marker produces silent action."""
        actions = parse_response("[thinking] I should work on...")
        assert len(actions) == 1
        assert actions[0].type == "silent"

    def test_json_single_action(self):
        """JSON with single action is parsed correctly."""
        text = '{"actions": [{"type": "react", "emoji": "👀"}]}'
        actions = parse_response(text)
        assert len(actions) == 1
        assert actions[0].type == "react"
        assert actions[0].emoji == "👀"

    def test_json_multiple_actions(self):
        """JSON with multiple actions preserves order."""
        text = '''{"actions": [
            {"type": "react", "emoji": "👀"},
            {"type": "message", "content": "Working on it..."},
            {"type": "react", "emoji": "✅"}
        ]}'''
        actions = parse_response(text)
        assert len(actions) == 3
        assert actions[0] == DiscordAction(type="react", emoji="👀")
        assert actions[1] == DiscordAction(type="message", content="Working on it...")
        assert actions[2] == DiscordAction(type="react", emoji="✅")

    def test_json_in_code_block(self):
        """JSON wrapped in markdown code block is parsed."""
        text = '''```json
{"actions": [{"type": "reply", "content": "Done!"}]}
```'''
        actions = parse_response(text)
        assert len(actions) == 1
        assert actions[0].type == "reply"
        assert actions[0].content == "Done!"

    def test_json_in_plain_code_block(self):
        """JSON in code block without json specifier works."""
        text = '''```
{"actions": [{"type": "react", "emoji": "🎄"}]}
```'''
        actions = parse_response(text)
        assert len(actions) == 1
        assert actions[0].emoji == "🎄"

    def test_invalid_json_becomes_reply(self):
        """Invalid JSON is treated as plain text reply."""
        text = '{"actions": [broken json'
        actions = parse_response(text)
        assert len(actions) == 1
        assert actions[0].type == "reply"
        assert actions[0].content == text

    def test_json_array_format(self):
        """Direct array format (without wrapper) works."""
        text = '[{"type": "react", "emoji": "👍"}]'
        actions = parse_response(text)
        assert len(actions) == 1
        assert actions[0].type == "react"
        assert actions[0].emoji == "👍"

    def test_action_types(self):
        """All action types are parsed correctly."""
        text = '''{"actions": [
            {"type": "react", "emoji": "👀"},
            {"type": "message", "content": "Channel message"},
            {"type": "reply", "content": "Direct reply"},
            {"type": "silent"}
        ]}'''
        actions = parse_response(text)
        assert len(actions) == 4
        assert actions[0].type == "react"
        assert actions[1].type == "message"
        assert actions[2].type == "reply"
        assert actions[3].type == "silent"

    def test_preserves_whitespace_in_content(self):
        """Whitespace in message content is preserved."""
        text = '{"actions": [{"type": "message", "content": "Line 1\\nLine 2"}]}'
        actions = parse_response(text)
        assert actions[0].content == "Line 1\nLine 2"

    def test_mixed_text_and_json(self):
        """If JSON is embedded in text, it should be extracted."""
        text = '''Here's my response:
```json
{"actions": [{"type": "react", "emoji": "✅"}]}
```
That's all!'''
        actions = parse_response(text)
        # Should extract the JSON
        assert len(actions) == 1
        assert actions[0].type == "react"
