import os
import subprocess
from datetime import datetime
from config import MONGODB_URI, MONGODB_DATABASE

def backup_database():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    backup_dir = os.path.join("backups", timestamp)

    os.makedirs(backup_dir, exist_ok=True)

    command = [
        "mongodump",
        f"--uri={MONGODB_URI}",
        f"--db={MONGODB_DATABASE}",
        f"--out={backup_dir}",
    ]

    subprocess.run(command, check=True)

    print(f"Database backup completed: {backup_dir}")