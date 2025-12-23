"""Job scheduler using APScheduler for precise timing.

Provides cron-style scheduling, intervals, and one-time jobs.
Jobs persist to disk and survive restarts.
"""

import json
import os
import re
from collections.abc import Callable, Coroutine
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

log = structlog.get_logger()


def _get_jobs_file() -> Path:
    """Get the jobs metadata file path."""
    env_path = os.environ.get("LARES_JOBS_FILE")
    if env_path:
        return Path(env_path)
    data_dir = os.environ.get("LARES_DATA_DIR", os.path.expanduser("~/.lares"))
    return Path(data_dir) / "scheduled_jobs.json"


class JobScheduler:
    """
    Manages scheduled jobs with APScheduler.

    Jobs are stored with metadata (prompt, description) in a JSON file,
    while APScheduler handles the actual timing.
    """

    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler(
            jobstores={"default": MemoryJobStore()},
            timezone="UTC",
        )
        self._jobs_file = _get_jobs_file()
        self._job_callback: Callable[[str, str], Coroutine[Any, Any, None]] | None = None
        self._job_metadata: dict[str, dict[str, Any]] = {}

    def set_callback(
        self, callback: Callable[[str, str], Coroutine[Any, Any, None]]
    ) -> None:
        """
        Set the callback for when jobs fire.

        Args:
            callback: Async function(job_id, prompt) called when a job triggers
        """
        self._job_callback = callback

    def start(self) -> None:
        """Start the scheduler and load persisted jobs."""
        if self._scheduler.running:
            log.debug("scheduler_already_running")
            return
        self._load_jobs()
        self._scheduler.start()
        log.info("scheduler_started", job_count=len(self._job_metadata))

    def shutdown(self) -> None:
        """Shut down the scheduler."""
        self._scheduler.shutdown(wait=False)
        log.info("scheduler_shutdown")

    def _load_jobs(self) -> None:
        """Load jobs from the persistence file."""
        if not self._jobs_file.exists():
            return

        try:
            data = json.loads(self._jobs_file.read_text())
            for job_data in data:
                job_id = job_data.get("id")
                if not job_id or not job_data.get("enabled", True):
                    continue

                # Store metadata
                self._job_metadata[job_id] = job_data

                # Recreate the APScheduler job
                schedule = job_data.get("schedule", "")
                prompt = job_data.get("prompt", "")

                trigger = self._parse_schedule(schedule)
                if trigger:
                    self._scheduler.add_job(
                        self._fire_job,
                        trigger=trigger,
                        id=job_id,
                        args=[job_id, prompt],
                        replace_existing=True,
                    )
                    log.info("job_loaded", job_id=job_id, schedule=schedule)

        except Exception as e:
            log.error("jobs_load_failed", error=str(e))

    def _save_jobs(self) -> None:
        """Save jobs metadata to file."""
        self._jobs_file.parent.mkdir(parents=True, exist_ok=True)
        jobs_list = list(self._job_metadata.values())
        self._jobs_file.write_text(json.dumps(jobs_list, indent=2, default=str))

    def _parse_schedule(self, schedule: str) -> CronTrigger | DateTrigger | IntervalTrigger | None:
        """
        Parse a schedule string into an APScheduler trigger.

        Supports:
        - Cron: "0 9 * * *" (9 AM daily), "0 9 * * MON-FRI" (weekdays)
        - ISO datetime: "2025-12-25T09:00:00" (one-time)
        - Intervals: "every 2 hours", "every 30 minutes"

        Cron format (5 fields):
            minute hour day_of_month month day_of_week

        Examples:
            "0 9 * * *"       - 9:00 AM UTC daily
            "30 14 * * MON"   - 2:30 PM UTC every Monday
            "0 0 1 * *"       - Midnight on 1st of each month
            "*/15 * * * *"    - Every 15 minutes
            "0 9 * * MON-FRI" - 9 AM UTC on weekdays
        """
        schedule = schedule.strip()

        # Try ISO datetime first (one-time jobs)
        # Format: YYYY-MM-DDTHH:MM:SS or similar
        if "T" in schedule and schedule.count("-") >= 2:
            try:
                dt = datetime.fromisoformat(schedule)
                return DateTrigger(run_date=dt)
            except ValueError:
                pass

        # Try interval patterns before cron (to avoid confusion)
        schedule_lower = schedule.lower()
        if "every" in schedule_lower:
            # "every N hours"
            match = re.search(r"every\s+(\d+)\s+hour", schedule_lower)
            if match:
                return IntervalTrigger(hours=int(match.group(1)))

            # "every N minutes"
            match = re.search(r"every\s+(\d+)\s+minute", schedule_lower)
            if match:
                return IntervalTrigger(minutes=int(match.group(1)))

            # "every N days"
            match = re.search(r"every\s+(\d+)\s+day", schedule_lower)
            if match:
                return IntervalTrigger(days=int(match.group(1)))

            # "every hour"
            if "every hour" in schedule_lower:
                return IntervalTrigger(hours=1)

            # "every day" or "daily"
            if "every day" in schedule_lower or "daily" in schedule_lower:
                return IntervalTrigger(days=1)

        # Try cron expression (5 or 6 space-separated fields)
        # Let APScheduler validate - it handles named days (MON-FRI),
        # step values (*/15), ranges (1-5), and lists (1,15)
        parts = schedule.split()
        if len(parts) in (5, 6):
            try:
                # APScheduler's from_crontab handles standard 5-field cron
                return CronTrigger.from_crontab(schedule)
            except ValueError as e:
                log.debug("cron_parse_failed", schedule=schedule, error=str(e))

        log.warning("schedule_parse_failed", schedule=schedule)
        return None

    async def _fire_job(self, job_id: str, prompt: str) -> None:
        """Called when a job triggers."""
        log.info("job_fired", job_id=job_id)

        # Update last_run
        if job_id in self._job_metadata:
            self._job_metadata[job_id]["last_run"] = datetime.now().isoformat()

            # Disable one-time jobs (datetime-based)
            schedule = self._job_metadata[job_id].get("schedule", "")
            if "T" in schedule and schedule.count("-") >= 2:
                self._job_metadata[job_id]["enabled"] = False
                # Remove from APScheduler too
                try:
                    self._scheduler.remove_job(job_id)
                except Exception:
                    pass

            self._save_jobs()

        # Call the callback
        if self._job_callback:
            try:
                await self._job_callback(job_id, prompt)
            except Exception as e:
                log.error("job_callback_failed", job_id=job_id, error=str(e))

    def add_job(
        self,
        job_id: str,
        prompt: str,
        schedule: str,
        description: str = "",
    ) -> str:
        """
        Schedule a new job.

        Args:
            job_id: Unique identifier
            prompt: Message to send to agent when job fires
            schedule: Cron, datetime, or interval string
            description: Human-readable description

        Returns:
            Success or error message
        """
        if job_id in self._job_metadata:
            return f"Error: Job '{job_id}' already exists. Remove it first."

        trigger = self._parse_schedule(schedule)
        if not trigger:
            return f"Error: Could not parse schedule '{schedule}'"

        # Store metadata
        self._job_metadata[job_id] = {
            "id": job_id,
            "prompt": prompt,
            "schedule": schedule,
            "description": description,
            "created_at": datetime.now().isoformat(),
            "last_run": None,
            "enabled": True,
        }

        # Add to APScheduler
        self._scheduler.add_job(
            self._fire_job,
            trigger=trigger,
            id=job_id,
            args=[job_id, prompt],
            replace_existing=True,
        )

        self._save_jobs()
        log.info("job_added", job_id=job_id, schedule=schedule)

        # Get next run time
        job = self._scheduler.get_job(job_id)
        next_run = getattr(job, "next_run_time", None) if job else None
        next_run_str = next_run.strftime("%Y-%m-%d %H:%M UTC") if next_run else "unknown"

        return f"Job '{job_id}' scheduled. Next run: {next_run_str}"

    def remove_job(self, job_id: str) -> str:
        """Remove a scheduled job."""
        if job_id not in self._job_metadata:
            return f"Error: Job '{job_id}' not found"

        del self._job_metadata[job_id]

        try:
            self._scheduler.remove_job(job_id)
        except Exception:
            pass  # Job might not be in APScheduler

        self._save_jobs()
        log.info("job_removed", job_id=job_id)
        return f"Job '{job_id}' removed"

    def list_jobs(self) -> str:
        """List all scheduled jobs with their next run times."""
        if not self._job_metadata:
            return "No scheduled jobs"

        lines = ["**Scheduled Jobs:**"]
        for job_id, meta in self._job_metadata.items():
            status = "✅" if meta.get("enabled", True) else "⏸️"
            schedule = meta.get("schedule", "?")
            desc = meta.get("description") or meta.get("prompt", "")[:50]
            last_run = meta.get("last_run", "never")

            # Get next run time from APScheduler
            job = self._scheduler.get_job(job_id)
            if job and getattr(job, "next_run_time", None):
                next_run = getattr(job, "next_run_time").strftime("%Y-%m-%d %H:%M UTC")
            else:
                next_run = "N/A"

            lines.append(f"{status} **{job_id}** - `{schedule}`")
            lines.append(f"   {desc}")
            lines.append(f"   Next: {next_run} | Last: {last_run}")

        return "\n".join(lines)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        """Get job metadata by ID."""
        return self._job_metadata.get(job_id)


# Global scheduler instance
_scheduler: JobScheduler | None = None


def get_scheduler() -> JobScheduler:
    """Get or create the global scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = JobScheduler()
    return _scheduler
