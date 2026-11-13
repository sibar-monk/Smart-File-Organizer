"""Sort the files directly inside a folder by extension."""

import os
import time
from tempfile import NamedTemporaryFile
from datetime import datetime

from app_access import check_password, choose_folder


class FileOrganizer:
    CATEGORIES = {
        "Images": (".jpg", ".png", ".jpeg"),
        "Documents": (".pdf", ".docx", ".txt"),
        "Videos": (".mp4", ".mkv"),
        "Python Files": (".py",),
        "Others": (),
    }
    LOG_NAME = "file_organizer.log"
    LOG_TITLE = "SMART FILE ORGANIZER - FILE MOVE HISTORY"
    LOG_HEADER = LOG_TITLE + "\nDate and time (local) | Original file -> New location\n"
    LOCK_NAME = ".file_organizer.lock"
    PARTIAL_EXTENSIONS = (".crdownload", ".part", ".download")

    def __init__(self, folder):
        self.folder = os.path.abspath(os.path.expanduser(folder))

    def get_category(self, filename):
        extension = os.path.splitext(filename)[1].lower()
        for category, extensions in self.CATEGORIES.items():
            if extension in extensions:
                return category
        return "Others"

    def scan_files(self):
        with os.scandir(self.folder) as entries:
            filenames = sorted(
                entry.name for entry in entries
                if os.path.normcase(entry.name) not in (
                    os.path.normcase(self.LOG_NAME), os.path.normcase(self.LOCK_NAME)
                )
                and not entry.name.lower().startswith((".organizer-log-", ".env."))
                and entry.name.lower() not in {".env", ".organizer_password"}
                and not entry.name.lower().endswith(self.PARTIAL_EXTENSIONS)
                and entry.is_file(follow_symlinks=False)
            )
        return filenames

    def destination_paths(self, category, filename):
        """Yield the original name, then numbered alternatives."""
        directory = os.path.join(self.folder, category)
        self.check_directory(directory)
        stem, extension = os.path.splitext(filename)
        yield os.path.join(directory, filename)
        number = 1
        while True:
            yield os.path.join(directory, f"{stem}_{number}{extension}")
            number += 1

    @staticmethod
    def check_directory(directory):
        # Junctions on Windows can also point outside the selected folder.
        is_junction = getattr(os.path, "isjunction", lambda path: False)
        if os.path.islink(directory) or is_junction(directory):
            raise OSError(f"Category folder points elsewhere: {directory}")
        if os.path.lexists(directory) and not os.path.isdir(directory):
            raise OSError(f"Category path is already a file: {directory}")

    def move_file(self, source, destination):
        """Reserve an unused name before moving into it."""
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        try:
            with open(destination, "xb"):
                pass
        except FileExistsError:
            return False
        try:
            os.replace(source, destination)
        except OSError:
            os.unlink(destination)
            raise
        return True

    def organize(self, preview=True):
        filenames = self.scan_files()
        if preview or not filenames:
            self.process_files(filenames, preview=preview)
            return

        lock_path = os.path.join(self.folder, self.LOCK_NAME)
        try:
            with open(lock_path, "x"):
                pass
        except FileExistsError:
            print("This folder already has an organizer lock. Check for another run.")
            return

        try:
            log_path = os.path.join(self.folder, self.LOG_NAME)
            self.prepare_log(log_path)
            with open(log_path, "a", encoding="utf-8", errors="backslashreplace") as log:
                self.process_files(self.scan_files(), log)
            print(f"Move log: {log_path}")
        finally:
            os.unlink(lock_path)

    def prepare_log(self, log_path):
        """Add the heading once and preserve any earlier records."""
        if os.path.islink(log_path) or (
            os.path.lexists(log_path) and not os.path.isfile(log_path)
        ):
            raise OSError(f"Cannot open the move log safely: {log_path}")

        try:
            with open(log_path, "rb") as existing:
                if existing.readline().rstrip(b"\r\n") == self.LOG_TITLE.encode("utf-8"):
                    return
                existing.seek(0)
                history = existing.read()
        except FileNotFoundError:
            history = b""

        draft = NamedTemporaryFile(
            mode="wb", dir=self.folder, prefix=".organizer-log-", delete=False
        )
        try:
            with draft:
                draft.write(self.LOG_HEADER.encode("utf-8"))
                draft.write(history)
                if history and not history.endswith(b"\n"):
                    draft.write(b"\n")
            os.replace(draft.name, log_path)
        finally:
            if os.path.exists(draft.name):
                os.unlink(draft.name)

    def process_files(self, filenames, log=None, preview=False):
        counts = dict.fromkeys(self.CATEGORIES, 0)
        reserved = set()
        failed = 0
        print("Preview only" if preview else "Organizing files")

        for filename in filenames:
            category = self.get_category(filename)
            source = os.path.join(self.folder, filename)
            try:
                for destination in self.destination_paths(category, filename):
                    key = os.path.normcase(destination)
                    if key in reserved or os.path.lexists(destination):
                        continue
                    if preview or self.move_file(source, destination):
                        break
            except OSError as error:
                failed += 1
                print(f"Left {filename!r} in place because: {error}")
                continue

            reserved.add(key)
            counts[category] += 1
            relative_path = os.path.relpath(destination, self.folder)
            action = "Would move" if preview else "Moved"
            print(f"{action} {filename!r} -> {relative_path!r}")
            if log is not None:
                timestamp = datetime.now().isoformat(timespec="seconds")
                try:
                    log.write(f"{timestamp} | {filename!r} -> {relative_path!r}\n")
                    log.flush()
                except OSError as error:
                    print(f"Could not log the last move: {error}")
                    print("Stopped processing to avoid further unlogged moves.")
                    break

        self.print_summary(counts, len(filenames), failed, preview)

    @staticmethod
    def print_summary(counts, found, failed, preview):
        total = sum(counts.values())
        print("\nPreview results (no files were moved)" if preview else "\nSorting results")
        if not found:
            print("There are no files to sort in this folder.")
            return

        print(f"Files found to check: {found}")
        print(f"Files that would be moved: {total}" if preview else f"Files moved: {total}")
        if failed:
            reason = "no destination could be prepared" if preview else "the move could not be completed"
            print(f"Files left in place because {reason}: {failed}")
        remaining = found - total - failed
        if remaining:
            print(f"Files left unchecked because sorting stopped early: {remaining}")

        if total:
            print("Files by destination folder:")
            for category, count in counts.items():
                print(f"  {category}: {count}")


def run_timed_review(organizer):
    """Repeat a read-only preview until the user presses Ctrl+C."""
    raw = input("Minutes between reviews (Enter to cancel): ").strip()
    if not raw:
        return
    if not raw.isascii() or not raw.isdecimal() or len(raw) > 4 or not 1 <= int(raw) <= 1440:
        print("Enter a whole number from 1 to 1440.")
        return
    minutes = int(raw)
    print("Timed review previews moves. Your downloads stay in place.")
    print("Timed review started. Press Ctrl+C to return to the menu.")
    try:
        while True:
            print(f"Next check in {minutes} minute(s).", flush=True)
            time.sleep(minutes * 60)
            organizer.organize(preview=True)
    except KeyboardInterrupt:
        print("\nTimed review stopped.")


def run_menu():
    """Keep the organizer open until the user chooses Exit."""
    organizer = None
    while True:
        selected = organizer.folder if organizer else "(choose a folder first)"
        print(f"\nSelected folder: {selected}")
        print("1. Preview only\n2. Organize files\n3. Change folder\n4. Exit\n5. Timed review")
        choice = input("Choose an option [1]: ").strip() or "1"
        try:
            if choice == "4":
                return
            if choice == "3":
                folder = choose_folder()
                if folder is not None:
                    organizer = FileOrganizer(folder)
            elif choice in {"1", "2", "5"}:
                if organizer is None:
                    print("Choose option 3 to select a folder first.")
                elif choice == "1":
                    organizer.organize()
                elif choice == "5":
                    run_timed_review(organizer)
                else:
                    print("Check that you received the right files and their downloads are complete.")
                    print("Scan this folder with your system’s security tools first.")
                    print("Review the scan results before moving files.")
                    confirm = input("Move files in this folder? Type yes to confirm: ")
                    if confirm.strip().lower() == "yes":
                        organizer.organize(preview=False)
                        print("You can also scan the organized files as a follow-up.")
                    else:
                        print("Cancelled.")
            else:
                print("Choose 1, 2, 3, 4, or 5.")
        except (OSError, ValueError) as error:
            print(f"Could not complete the operation: {error}")


def main():
    print("Smart File Organizer")
    try:
        if check_password():
            run_menu()
    except (OSError, ValueError) as error:
        print(f"Could not start the organizer: {error}")
    except (EOFError, KeyboardInterrupt):
        print()
    print("Session ended.")


if __name__ == "__main__":
    main()
