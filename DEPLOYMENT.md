# Sukoon deployment and operations

Local daily backup is also scheduled in this Codex thread at 02:00. The computer/Codex app must be available; this does not replace server-side production scheduling.

Local development uses config.settings and explicit DJANGO_DEBUG=True in private .env.
Production uses DJANGO_SETTINGS_MODULE=config.production. It requires a unique secret and a dedicated non-root database user. Never copy local secrets to a public repository. Rotate previously hardcoded database credentials before production deployment.

## Deploy
1. Back up the existing production database and media. Run backup_project and verify_backup.
2. Install requirements.txt with the target server's virtual environment. Use Python compatible with Django 6.1.
3. Configure private environment variables from .env.example; set DJANGO_DEBUG=False and public domain/DB values.
4. Run python manage.py migrate --settings=config.production.
5. Run python manage.py setup_roles --settings=config.production.
6. Run python manage.py collectstatic --noinput --settings=config.production.
7. Run python manage.py check --deploy --settings=config.production. security.W021 is expected while browser HSTS preload is intentionally disabled; enable preload only after confirming long-term HTTPS coverage and owner approval.
8. Use a production WSGI/ASGI server; never expose runserver. On Windows, install Waitress and run waitress-serve --listen=127.0.0.1:8000 config.wsgi:application behind an HTTPS reverse proxy. On Linux, use Gunicorn behind nginx. Set DJANGO_SETTINGS_MODULE=config.production in the service environment.
9. Serve /static/ from staticfiles and /media/ from media; uploaded media must never execute as code. Do not serve data/, .env, or source files.
10. Redirect HTTP to HTTPS. Set TRUST_PROXY_HTTPS=True only if a trusted proxy removes client-supplied forwarding headers and sets X-Forwarded-Proto itself. Forward the real client IP only through a trusted server configuration; rate limiting uses REMOTE_ADDR.
11. Check /, /connect/, /book/, /login/, /privacy/, /sitemap.xml and /robots.txt on the public domain. Scan and print the reception QR after /connect/ returns 200.

## Access
Existing superusers retain access. setup_roles creates groups but never changes users.
Owner gets spa management/business analytics permissions.
Receptionist gets appointment/enquiry management and read-only treatment/staff/room access, without deletion or business-value analytics.
Only superusers manage auth users/groups. Assign roles and is_staff through Users as a superuser. Customers can only access their own appointments.

## Notifications (disabled until configured)
Set EMAIL_ENABLED=True only with working SMTP settings and BUSINESS_EMAIL.
Password resets send secure expiring links through the configured mailer; verification and booking emails use the outbox worker.
WhatsApp integration targets a Meta-compatible WhatsApp Business template API. Configure HTTPS API URL, access token, approved template name/language; the body parameters must match: customer name, treatment, appointment date, appointment time, event. Have the provider approve the template and confirm required consent before enabling.
Queued messages are provider-accepted, not proven delivered; no delivery webhook is implemented.
Run process_notifications once per minute after enabling providers. Inspect failed/processing jobs in admin. A worker crash after provider acceptance can leave a processing job; check provider logs before retrying to avoid duplicate messages.
Do not enable providers merely to test against real customers; use test recipients or mocked providers.

## Daily backup and restore
Run python manage.py backup_project --settings=config.production at 02:00 server local time using cron or Task Scheduler. Run verify_backup on the resulting ZIP.
Run process_notifications every minute. Schedule clearsessions weekly. Actual scheduler setup requires hosting access.
Example cron (replace paths):
0 2 * * * cd /srv/sukoon && /srv/sukoon/venv/bin/python manage.py backup_project --settings=config.production
* * * * * cd /srv/sukoon && /srv/sukoon/venv/bin/python manage.py process_notifications --settings=config.production
0 3 * * 0 cd /srv/sukoon && /srv/sukoon/venv/bin/python manage.py clearsessions --settings=config.production

Backups contain private customer data and password hashes. ZIP files are not encrypted: keep them outside the web root, restrict access, and copy them to encrypted offsite storage. Keep at least 30 daily backups; check storage and cleanup according to your retention policy.
The MySQL database dump is a consistent transactional snapshot; media is copied separately. Run during a quiet period and avoid schema changes/uploads during backup.
Restore drill: provision a separate empty database and a separate media directory; verify_backup, decompress database.sql.gz, import using the MySQL client, restore media/, and run migrations/checks against the restored database. SQL dumps replace tables: never import into the running production database without a verified backup and maintenance window. Confirm booking counts and logins in the separate restored environment before considering the drill complete.
Archive/checksum verification and an isolated local MySQL restore drill have passed. Repeat the restore drill against a separate production/staging environment once hosting access is available.

## Content and policies
The reviewed printed menu is stored in `spa/data/sukoon_rate_card.json`. After migrations and a backup, run `python manage.py sync_rate_card` to preview and `python manage.py sync_rate_card --apply` to apply it to the target database. Existing service IDs and booking price/name snapshots are preserved. The command deactivates options absent from the reviewed menu; it does not delete historical records. Body-care and multi-session package prices have no fabricated durations and are arranged through reception. Later business price changes should be managed in admin; do not reapply the printed menu unless intentionally restoring these rates.
Treatments/prices are database-managed. Treatments without active options show reception contact and are excluded from online booking; enter correct business prices/durations in admin rather than guessing them.
Leave Amount Paid blank when payment is unknown; enter 0 to record an unpaid booking. Payment records do not initiate charges or refunds.

Customer online cancellation/rescheduling closes two hours before appointment start. Cancellation does not perform automatic refunds.
Privacy and cancellation pages describe current behavior. Review the privacy retention wording and cancellation/payment handling with the proprietor before publishing.
