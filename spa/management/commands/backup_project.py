import gzip, hashlib, json, tempfile, zipfile
from datetime import datetime
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

class Command(BaseCommand):
    help = "Back up a consistent database snapshot and media files to a private ZIP archive."
    def add_arguments(self, parser):
        parser.add_argument("--directory",default=str(settings.BASE_DIR/"data"/"backups"))
    def handle(self,*args,**options):
        folder=Path(options["directory"]).resolve()
        folder.mkdir(parents=True,exist_ok=True)
        target=folder/("sukoon-"+datetime.now().strftime("%Y%m%d-%H%M%S-%f")+".zip")
        with tempfile.TemporaryDirectory(prefix="sukoon-backup-") as tmp:
            sql=Path(tmp)/"database.sql.gz"
            connection.ensure_connection()
            with gzip.open(sql,"wb") as out:
                if connection.vendor=="sqlite":
                    for statement in connection.connection.iterdump():
                        out.write((statement+"\n").encode())
                elif connection.vendor=="mysql":
                    cursor=connection.cursor()
                    try:
                        owns_transaction = not connection.in_atomic_block
                        if owns_transaction:
                            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                            cursor.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY")
                        out.write(b"SET NAMES utf8mb4;\nSET SQL_MODE='NO_AUTO_VALUE_ON_ZERO';\nSET TIME_ZONE='+00:00';\nSET FOREIGN_KEY_CHECKS=0;\n")
                        tables=connection.introspection.table_names(cursor)
                        for table in tables:
                            quoted=connection.ops.quote_name(table)
                            cursor.execute("SHOW CREATE TABLE "+quoted)
                            schema=cursor.fetchone()[1]
                            out.write(("DROP TABLE IF EXISTS "+quoted+";\n"+schema+";\n").encode())
                            cursor.execute("SELECT * FROM "+quoted)
                            while True:
                                rows=cursor.fetchmany(500)
                                if not rows:break
                                for row in rows:
                                    literals=[connection.connection.literal(value) for value in row]
                                    out.write(("INSERT INTO "+quoted+" VALUES (").encode()+b",".join(literals)+b");\n")
                        out.write(b"SET FOREIGN_KEY_CHECKS=1;\n")
                    finally:
                        if owns_transaction: cursor.execute("ROLLBACK")
                        cursor.close()
                else:
                    raise CommandError("Backup supports MySQL and SQLite.")
            manifest={"database_vendor":connection.vendor,"created_at":datetime.now().isoformat(),"database_sha256":hashlib.sha256(sql.read_bytes()).hexdigest(),"media":[]}
            with zipfile.ZipFile(target,"x",zipfile.ZIP_DEFLATED) as archive:
                archive.write(sql,"database.sql.gz")
                if settings.MEDIA_ROOT.exists():
                    for file in settings.MEDIA_ROOT.rglob("*"):
                        if file.is_file() and not file.is_symlink():
                            relative=file.relative_to(settings.MEDIA_ROOT).as_posix()
                            archive.write(file,"media/"+relative)
                            manifest["media"].append({"path":relative,"sha256":hashlib.sha256(file.read_bytes()).hexdigest()})
                archive.writestr("manifest.json",json.dumps(manifest,indent=2))
        self.stdout.write(self.style.SUCCESS(str(target)))
