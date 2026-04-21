# Time-Tracker
.env example:

POSTGRES_USER=admin
POSTGRES_PASSWORD=yourdbpassword
POSTGRES_DB=timetracker
DATABASE_URL=postgresql+asyncpg://admin:yourdbpassword@db:5432/timetracker
ADMIN_PASSWORD=youradminpassword

If you need to restore the database from a dump, run the following command (on the host):

docker exec -i timetrek-db-1 psql -U admin timetracker < backups/filename.sql

In docker-compose.yml:
  app:
    environment:
      TZ: Asia/Yerevan <- write down your own time zone