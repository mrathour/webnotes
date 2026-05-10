import json
import subprocess
import sys
from pathlib import Path
from notes_db import init_db, sync_saved_folder, sync_notes_folder, get_files_without_notes, mark_note_created


def main():
    init_db()
    sync_saved_folder()
    sync_notes_folder()  # pick up notes already created outside this script

    pending = get_files_without_notes()
    if not pending:
        print("All captures already have notes.")
        return

    print(f"{len(pending)} file(s) pending:")
    for stem in pending:
        print(f"  -> {stem}")

    notes_dir = Path(__file__).parent / "notes"
    saved_dir = Path(__file__).parent / "backend" / "saved"

    print()
    total_in = total_out = 0
    for stem in pending:
        print(f"Processing: {stem} ...", end=" ", flush=True)
        result = subprocess.run(
            [
                "claude", "-p",
                f"/make-notes {stem} {saved_dir} {notes_dir}",
                "--output-format", "json",
                "--allowedTools", "Read,Write",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            input_tokens = output_tokens = None
            try:
                data = json.loads(result.stdout)
                usage = data.get("usage", {})
                input_tokens = usage.get("input_tokens")
                output_tokens = usage.get("output_tokens")
                if input_tokens:
                    total_in += input_tokens
                if output_tokens:
                    total_out += output_tokens
            except (json.JSONDecodeError, AttributeError):
                pass
            mark_note_created(stem, input_tokens, output_tokens)
            token_info = f"  [{input_tokens} in / {output_tokens} out]" if input_tokens else ""
            print(f"done{token_info}")
        else:
            print(f"FAILED\n{result.stderr.strip()}")
            sys.exit(1)

    if total_in or total_out:
        print(f"\nTotal tokens: {total_in} in / {total_out} out")


if __name__ == "__main__":
    main()
