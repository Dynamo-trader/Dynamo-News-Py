from apscheduler.job import Job
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.config import Var

schedule = AsyncIOScheduler()
job_defaults = {"coalesce": False, "max_instances": 1}
schedule.configure(timezone=Var.TZ, job_defaults=job_defaults)
schedule_ids: list[Job] = []