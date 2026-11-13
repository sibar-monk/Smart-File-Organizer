"""Password verification and folder selection for the terminal app."""

import hashlib
import hmac
import os
from getpass import getpass
from pathlib import Path

from dotenv import dotenv_values, set_key


ENV_FILE = Path(__file__).resolve().with_name(".env")


def password_digest(password, salt):
    """Derive the verifier stored in .env."""
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=16384, r=8, p=1)


def check_password():
    """Set a password on first use or verify the saved hash."""
    settings = dotenv_values(ENV_FILE, interpolate=False, encoding="utf-8-sig")
    stored = settings.get("ORGANIZER_PASSWORD_HASH")
    if "ORGANIZER_PASSWORD" in settings:
        print("Old plaintext password setting found. To upgrade, delete the")
        print("ORGANIZER_PASSWORD line from your private .env, then restart.")
        return False

    if not stored:
        password = getpass("Create an organizer password (Enter to exit): ")
        if not password:
            return False
        if len(password.strip()) < 8:
            print("Use at least eight characters and restart the organizer.")
            return False
        if password != getpass("Confirm your password: "):
            print("Passwords do not match. Restart to try again.")
            return False
        salt = os.urandom(16)
        digest = password_digest(password, salt)
        set_key(ENV_FILE, "ORGANIZER_PASSWORD_HASH", f"{salt.hex()}:{digest.hex()}",
                encoding="utf-8-sig")
        return True

    try:
        salt_text, digest_text = stored.split(":")
        salt, digest = bytes.fromhex(salt_text), bytes.fromhex(digest_text)
        if len(salt) != 16 or len(digest) != 64:
            raise ValueError
    except ValueError:
        print("Invalid password hash in .env. Check your local configuration.")
        return False

    while True:
        entered = getpass("Organizer password (Enter to exit): ")
        if not entered:
            return False
        if hmac.compare_digest(password_digest(entered, salt), digest):
            return True
        print("Incorrect password. Try again.")


def choose_folder():
    print("\n1. Choose a local or synced folder\n2. OneDrive folder\n3. Back")
    choice = input("Choose a folder type [1]: ").strip() or "1"
    if choice == "3":
        return None
    if choice not in {"1", "2"}:
        print("Choose 1, 2, or 3.")
        return None

    roots = []
    if choice == "2":
        for name in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
            value = os.environ.get(name)
            if value and Path(value).is_dir():
                root = Path(value).resolve()
                if root not in roots:
                    roots.append(root)
        if not roots:
            print("No OneDrive folder was detected. Check your cloud client or file manager.")
            print("You can also select its folder using option 1.")
            return None
        print("Detected OneDrive folders:")
        for root in roots:
            print(f"  {root}")
        print("Paste the full path of an existing source subfolder inside OneDrive.")

    raw_path = input("Folder path: ").strip().strip('"')
    if not raw_path:
        print("Enter a folder path and choose the folder again.")
        return None
    try:
        folder = Path(raw_path).expanduser().resolve()
    except RuntimeError:
        print("Could not resolve this folder path.")
        return None
    if not folder.is_dir():
        print("The path must point to an existing folder.")
        return None
    if roots and not any(root in folder.parents for root in roots):
        print("Choose a subfolder inside one of the detected OneDrive folders.")
        return None
    if folder == Path(__file__).resolve().parent:
        print("Choose a test or work folder outside the app's own folder.")
        return None
    return folder
