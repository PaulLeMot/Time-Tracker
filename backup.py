import os
import subprocess
import asyncio
from datetime import datetime
from pathlib import Path
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

BACKUP_DIR = Path("/app/backups")
BACKUP_DIR.mkdir(exist_ok=True)

async def run_backup():
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_file = BACKUP_DIR / f"timetracker_{timestamp}.sql"
    
    env = os.environ.copy()
    env["PGPASSWORD"] = os.getenv("POSTGRES_PASSWORD", "")
    
    cmd = [
        "pg_dump",
        "-h", "db",
        "-U", "admin",
        "-d", "timetracker",
        "-f", str(backup_file)
    ]
    
    try:
        result = subprocess.run(cmd, env=env, stderr=subprocess.PIPE, text=True, check=True)
        print(f"Backup created: {backup_file}")
        #last 10 backups stay
        backups = sorted(BACKUP_DIR.glob("timetracker_*.sql"))
        for old in backups[:-10]:
            old.unlink()
    except subprocess.CalledProcessError as e:
        print(f"Backup failed: {e.stderr}")

def schedule_backup():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(run_backup, CronTrigger(hour=2, minute=0))
    scheduler.start()