"""Scheduler tool wrappers for Letta.

These functions wrap the JobScheduler to provide tools that can be
called by the agent to schedule/manage jobs.
"""

from lares.scheduler import get_scheduler


def schedule_job(
    job_id: str,
    prompt: str,
    schedule: str,
    description: str = "",
) -> str:
    """
    Schedule a job to trigger the agent with a prompt.

    Args:
        job_id: Unique identifier for the job (used to remove it later)
        prompt: The prompt to send to the agent when the job triggers
        schedule: When to run - supports:
            - Cron expression: "0 9 * * *" (9 AM UTC daily)
            - ISO datetime for one-time: "2025-12-25T09:00:00"
            - Intervals: "every 2 hours", "every 30 minutes"
        description: Human-readable description of what this job does

    Returns:
        Success message with next run time, or error message

    Examples:
        # Daily 9 AM UTC reminder
        schedule_job("morning-check", "Good morning! Review today's tasks.", "0 9 * * *")

        # One-time reminder
        schedule_job("xmas", "Merry Christmas!", "2025-12-25T00:00:00")

        # Every 4 hours
        schedule_job("health-check", "Check system status", "every 4 hours")
    """
    scheduler = get_scheduler()
    return scheduler.add_job(job_id, prompt, schedule, description)


def remove_job(job_id: str) -> str:
    """
    Remove a scheduled job.

    Args:
        job_id: The ID of the job to remove

    Returns:
        Success or error message
    """
    scheduler = get_scheduler()
    return scheduler.remove_job(job_id)


def list_jobs() -> str:
    """
    List all scheduled jobs with their next run times.

    Returns:
        Formatted list of jobs with status, schedule, and timing info
    """
    scheduler = get_scheduler()
    return scheduler.list_jobs()
