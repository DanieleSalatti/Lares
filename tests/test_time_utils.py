"""Tests for time_utils module."""

from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from lares.time_utils import get_time_context, get_user_date, get_user_time_of_day


class TestGetTimeContext:
    """Tests for get_time_context function."""

    def test_returns_both_timezones(self):
        """Should include both user timezone and UTC in the output."""
        result = get_time_context("America/Los_Angeles")
        assert "(PST)" in result or "(PDT)" in result  # Depends on DST
        assert "(UTC)" in result

    def test_format_includes_date_and_time(self):
        """Should include formatted date and time."""
        result = get_time_context()
        # Check it has day of week
        assert any(day in result for day in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
        # Check it has AM or PM
        assert "AM" in result or "PM" in result

    def test_invalid_timezone_falls_back_to_utc(self):
        """Invalid timezone should fall back to UTC-only format."""
        result = get_time_context("Invalid/Timezone")
        assert "(UTC)" in result
        # Should not have a second timezone since fallback is UTC-only
        assert result.count("(") == 1


class TestGetUserDate:
    """Tests for get_user_date function."""

    @patch("lares.time_utils.datetime")
    def test_returns_formatted_date(self, mock_datetime):
        """Should return date in 'Month DD, YYYY' format."""
        mock_now = datetime(2025, 12, 25, 15, 0, 0, tzinfo=ZoneInfo("UTC"))
        mock_datetime.now.return_value = mock_now

        result = get_user_date("America/Los_Angeles")
        assert result == "December 25, 2025"

    def test_invalid_timezone_returns_utc_date(self):
        """Invalid timezone should return UTC date."""
        result = get_user_date("Invalid/Timezone")
        # Should still return a valid date format
        assert "," in result  # Has comma separator
        assert "20" in result  # Has year


class TestGetUserTimeOfDay:
    """Tests for get_user_time_of_day function."""

    @patch("lares.time_utils.datetime")
    def test_morning(self, mock_datetime):
        """Hours 5-11 should return 'morning'."""
        mock_now = datetime(2025, 12, 25, 16, 0, 0, tzinfo=ZoneInfo("UTC"))  # 8 AM PST
        mock_datetime.now.return_value = mock_now

        result = get_user_time_of_day("America/Los_Angeles")
        assert result == "morning"

    @patch("lares.time_utils.datetime")
    def test_afternoon(self, mock_datetime):
        """Hours 12-16 should return 'afternoon'."""
        mock_now = datetime(2025, 12, 25, 22, 0, 0, tzinfo=ZoneInfo("UTC"))  # 2 PM PST
        mock_datetime.now.return_value = mock_now

        result = get_user_time_of_day("America/Los_Angeles")
        assert result == "afternoon"

    @patch("lares.time_utils.datetime")
    def test_evening(self, mock_datetime):
        """Hours 17-20 should return 'evening'."""
        mock_now = datetime(2025, 12, 26, 1, 0, 0, tzinfo=ZoneInfo("UTC"))  # 5 PM PST
        mock_datetime.now.return_value = mock_now

        result = get_user_time_of_day("America/Los_Angeles")
        assert result == "evening"

    @patch("lares.time_utils.datetime")
    def test_night(self, mock_datetime):
        """Hours 21-4 should return 'night'."""
        mock_now = datetime(2025, 12, 26, 7, 0, 0, tzinfo=ZoneInfo("UTC"))  # 11 PM PST
        mock_datetime.now.return_value = mock_now

        result = get_user_time_of_day("America/Los_Angeles")
        assert result == "night"

    def test_invalid_timezone_returns_day(self):
        """Invalid timezone should return 'day' as safe fallback."""
        result = get_user_time_of_day("Invalid/Timezone")
        assert result == "day"
