# ReMixamo Downloader

A GUI tool to bulk download animations from Mixamo — forked from [juanjo4martinez/mixamo-downloader](https://github.com/juanjo4martinez/mixamo-downloader) with significant reliability improvements.

---

## What's different in this fork

The original version would reliably freeze and hang after approximately 200–400 downloads. This fork fixes that and adds several other improvements:

- **Freeze fix** — the original poll loop had no exit condition, so a stalled Mixamo export job would hang the app indefinitely. The loop is now capped with a configurable timeout.
- **Hang detection and auto-retry** — if an export job times out, the tool waits a backoff period (starting at 3 minutes, doubling each retry) and then re-submits the job from scratch. Up to 5 retries per animation by default, making overnight runs far more likely to complete fully.
- **S3 URL expiry handling** — Mixamo's export URLs expire after 5 minutes. If the download fails because the URL expired, the tool automatically re-submits the export job to get a fresh URL rather than writing a corrupt file to disk.
- **Corrupt file detection** — any file under 10KB is treated as a corrupt download and will be automatically re-downloaded on the next run.
- **Rate limit handling** — HTTP 429 and 503 responses are now detected and handled with exponential backoff instead of silently failing.
- **Request timeouts** — all API calls now have connect and read timeouts so a stalled connection can never hang the app.
- **Skip already-downloaded files** — on resume, the tool checks whether each FBX already exists on disk and is a valid size before making any API calls, so interrupted runs can be safely restarted without re-downloading everything.
- **Name cache** — a `mixamo_name_cache.json` file is maintained alongside the app to map animation IDs to their real filenames. This is pre-populated from the animation page listing at startup with no extra API calls, allowing instant skip checks on subsequent runs.
- **Live animation list** — the tool now queries the Mixamo API directly for the full animation list instead of relying on a static bundled JSON file, so newly added Mixamo animations are always picked up. The `mixamo_anims.json` file is no longer required or used.
- **Windows filename sanitization** — animation names containing characters illegal in Windows filenames (such as `/` in *"Laying Down On An Exam Table/Bed As In A Doctors Office"*) are now sanitized automatically instead of crashing.
- **FBX for Unity format** — exports use the `fbx7_unity` format at 30fps without skin, matching Mixamo's own Unity export settings.
- **PySide6 compatibility** — updated to work with PySide6 and Python 3.14+.

---

## Requirements

- Python 3.14+
- PySide6
- requests

---

## For Python users

Install the required packages:

```
pip install PySide6
pip install requests
```

Download the files from the `/src` folder to your own local directory and double-click `main.pyw` to launch the GUI. If double-clicking doesn't work, run it from a terminal:

```
python main.pyw
```

---

## For non-technical users

Download the `/dist` folder to your computer and run `mixamo_downloader.exe`. Keep all files in the folder together — do not move the `.exe` on its own.

---

## How to use

1. Log into your Mixamo account inside the built-in browser.

2. Select or upload the character you want to animate.

3. Choose a download mode:
   - **All animations** — downloads every animation currently available on Mixamo.
   - **Animations containing the word** — searches Mixamo and downloads only matching results.
   - **T-Pose (with skin)** — downloads just the T-Pose with the character mesh included.

4. Optionally set an output folder where FBX files will be saved. If no folder is set, files are saved to the folder the program is running from.

5. Press **Start download** and let it run. You can leave it running overnight — the hang detection and auto-retry logic will handle any stalls automatically.

6. Press **Stop** at any time to cancel. The next run will automatically skip any files already downloaded.

---

## Resuming an interrupted run

Simply run the tool again with the same output folder selected. Any FBX files already present in that folder will be detected and skipped automatically. Only missing or corrupt files will be downloaded.

---

## Notes

- Downloading all animations is slow by design — Mixamo has over 2000 animations and each one requires its own export job on their servers. Expect a full run to take several hours.
- The `mixamo_name_cache.json` file is stored alongside the app (not in your download folder). Do not delete it if you want fast skip detection on future runs — though it will simply be rebuilt on the next full run if it is missing.
- All animations are downloaded without skin to save space. The T-Pose mode is the only option that includes the character mesh.
- The `mixamo_anims.json` file included in the original repo is no longer used and can be safely deleted.

---

## Credits

Original tool by [juanjo4martinez](https://github.com/juanjo4martinez/mixamo-downloader). Reliability improvements and PySide6 port by [amalgamemnon](https://github.com/amalgamemnon).
