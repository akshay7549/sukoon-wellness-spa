import hashlib,json,zipfile
from pathlib import PurePosixPath
from django.core.management.base import BaseCommand, CommandError

class Command(BaseCommand):
    help = "Verify database/media backup integrity without restoring or changing data."
    def add_arguments(self,parser):parser.add_argument("archive")
    def handle(self,*args,**options):
        try:
            with zipfile.ZipFile(options["archive"]) as z:
                for name in z.namelist():
                    path=PurePosixPath(name)
                    if path.is_absolute() or ".." in path.parts or "\\" in name:
                        raise CommandError("Unsafe archive path.")
                manifest=json.loads(z.read("manifest.json"))
                if hashlib.sha256(z.read("database.sql.gz")).hexdigest()!=manifest["database_sha256"]:
                    raise CommandError("Database integrity check failed.")
                for item in manifest["media"]:
                    if hashlib.sha256(z.read("media/"+item["path"])).hexdigest()!=item["sha256"]:
                        raise CommandError("Media integrity check failed.")
        except (OSError,KeyError,ValueError,zipfile.BadZipFile) as exc:
            raise CommandError("Invalid backup archive.") from exc
        self.stdout.write(self.style.SUCCESS("Database and media checksums verified."))
