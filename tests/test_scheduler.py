"""Tests for the job scheduler."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from lares.scheduler import JobScheduler


class TestJobScheduler:
    """Tests for JobScheduler class."""

    @pytest.fixture
    def temp_jobs_file(self, tmp_path):
        """Create a temporary jobs file."""
        jobs_file = tmp_path / "jobs.json"
        return jobs_file

    @pytest.fixture
    def scheduler(self, temp_jobs_file):
        """Create a scheduler with temporary storage."""
        with patch.dict("os.environ", {"LARES_JOBS_FILE": str(temp_jobs_file)}):
            return JobScheduler()

    def test_init(self, scheduler):
        """Scheduler initializes correctly."""
        assert scheduler._scheduler is not None
        assert scheduler._job_metadata == {}

    def test_set_callback(self, scheduler):
        """Can set job callback."""
        callback = AsyncMock()
        scheduler.set_callback(callback)
        assert scheduler._job_callback == callback

    @pytest.mark.asyncio
    async def test_add_job_interval(self, scheduler, temp_jobs_file):
        """Can add an interval job."""
        with patch.dict("os.environ", {"LARES_JOBS_FILE": str(temp_jobs_file)}):
            scheduler.start()
            try:
                result = scheduler.add_job(
                    job_id="interval-job",
                    prompt="Test prompt",
                    schedule="every 1 hours",
                    description="Test interval job",
                )
                # Returns success message string
                assert "scheduled" in result
                assert "interval-job" in result
                assert "interval-job" in scheduler._job_metadata

                # Check persistence
                assert temp_jobs_file.exists()
                data = json.loads(temp_jobs_file.read_text())
                assert any(j.get("id") == "interval-job" for j in data)
            finally:
                scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_add_job_daily(self, scheduler, temp_jobs_file):
        """Can add a daily cron job."""
        with patch.dict("os.environ", {"LARES_JOBS_FILE": str(temp_jobs_file)}):
            scheduler.start()
            try:
                result = scheduler.add_job(
                    job_id="daily-job",
                    prompt="Daily prompt",
                    schedule="every day at 09:00",
                    description="Daily job",
                )
                assert "scheduled" in result
                assert "daily-job" in scheduler._job_metadata
            finally:
                scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_add_job_invalid_schedule(self, scheduler, temp_jobs_file):
        """Invalid schedule returns error message."""
        with patch.dict("os.environ", {"LARES_JOBS_FILE": str(temp_jobs_file)}):
            scheduler.start()
            try:
                result = scheduler.add_job(
                    job_id="bad-job",
                    prompt="Bad",
                    schedule="whenever",
                )
                assert "Error" in result
                assert "bad-job" not in scheduler._job_metadata
            finally:
                scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_remove_job(self, scheduler, temp_jobs_file):
        """Can remove a scheduled job."""
        with patch.dict("os.environ", {"LARES_JOBS_FILE": str(temp_jobs_file)}):
            scheduler.start()
            try:
                scheduler.add_job(
                    job_id="remove-me",
                    prompt="Test",
                    schedule="every 2 hours",
                )
                assert "remove-me" in scheduler._job_metadata

                result = scheduler.remove_job("remove-me")
                assert "removed" in result
                assert "remove-me" not in scheduler._job_metadata
            finally:
                scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_remove_nonexistent_job(self, scheduler, temp_jobs_file):
        """Removing nonexistent job returns error."""
        with patch.dict("os.environ", {"LARES_JOBS_FILE": str(temp_jobs_file)}):
            scheduler.start()
            try:
                result = scheduler.remove_job("does-not-exist")
                assert "not found" in result
            finally:
                scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_list_jobs(self, scheduler, temp_jobs_file):
        """Can list all jobs."""
        with patch.dict("os.environ", {"LARES_JOBS_FILE": str(temp_jobs_file)}):
            scheduler.start()
            try:
                scheduler.add_job("job1", "Prompt 1", "every 1 hours", "Job 1")
                scheduler.add_job("job2", "Prompt 2", "every 2 hours", "Job 2")

                result = scheduler.list_jobs()
                # Returns formatted string
                assert "job1" in result
                assert "job2" in result
            finally:
                scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_list_jobs_empty(self, scheduler, temp_jobs_file):
        """List jobs when empty returns appropriate message."""
        with patch.dict("os.environ", {"LARES_JOBS_FILE": str(temp_jobs_file)}):
            scheduler.start()
            try:
                result = scheduler.list_jobs()
                assert "No scheduled jobs" in result
            finally:
                scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_metadata_stored_correctly(self, scheduler, temp_jobs_file):
        """Job metadata is stored with all fields."""
        with patch.dict("os.environ", {"LARES_JOBS_FILE": str(temp_jobs_file)}):
            scheduler.start()
            try:
                scheduler.add_job(
                    job_id="meta-job",
                    prompt="Test prompt",
                    schedule="every 5 hours",
                    description="Meta test",
                )

                # Check internal metadata
                meta = scheduler._job_metadata["meta-job"]
                assert meta["prompt"] == "Test prompt"
                assert meta["schedule"] == "every 5 hours"
                assert meta["description"] == "Meta test"
            finally:
                scheduler.shutdown()
