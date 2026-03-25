# Stdlib modules
import json
import os
import requests
import time

# Third-party modules
from PySide6 import QtCore, QtWebEngineWidgets, QtWidgets


HEADERS = {
    "Accept": "application/json",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Content-Type": "application/json",
    "X-Api-Key": "mixamo2",
    "X-Requested-With": "XMLHttpRequest",
}

# All requests will be done through a session to improve performance.
session = requests.Session()

# ── Tunables ────────────────────────────────────────────────────────────────
# Seconds to wait between each animation download.  Raising this reduces the
# chance of hitting Mixamo's rate limiter.  1–2 s is a good default.
INTER_DOWNLOAD_DELAY = 1.5

# Maximum number of poll attempts before giving up on a single export job.
# Each attempt waits POLL_INTERVAL seconds, so the total timeout is
# MAX_POLL_ATTEMPTS × POLL_INTERVAL.  At 2 s each, 90 attempts = 3 minutes.
MAX_POLL_ATTEMPTS = 90
POLL_INTERVAL = 2  # seconds

# Connection / read timeouts for every requests call (seconds).
CONNECT_TIMEOUT = 15
READ_TIMEOUT = 60

# Maximum retries (with exponential back-off) for transient failures.
MAX_RETRIES = 5

# How many times to retry a single animation when the poll loop times out
# (i.e. a "hang" is detected).  On each retry the tool waits HANG_BACKOFF_BASE
# seconds before re-submitting the export job and restarting the poll loop from
# scratch.  The wait doubles on each successive hang: 3 min → 6 min → 12 min.
# Set to 0 to disable hang retries (old behaviour).
MAX_HANG_RETRIES = 5
HANG_BACKOFF_BASE = 180  # seconds (3 minutes)
# ────────────────────────────────────────────────────────────────────────────


def _get(url, **kwargs):
    """Wrapper around session.get() with timeout + exponential back-off retry.

    Handles:
    - Missing timeout (Bug 1 fix)
    - HTTP 429 / 503 rate-limit responses with back-off (Bug 2 fix)
    - Transient connection errors (timeouts, resets)
    """
    kwargs.setdefault("timeout", (CONNECT_TIMEOUT, READ_TIMEOUT))
    kwargs.setdefault("headers", HEADERS)

    for attempt in range(MAX_RETRIES):
        try:
            response = session.get(url, **kwargs)

            if response.status_code in (429, 503):
                wait = (2 ** attempt) * 10  # 10 s, 20 s, 40 s …
                print(f"[downloader] Rate limited ({response.status_code}). "
                      f"Waiting {wait} s before retry {attempt + 1}/{MAX_RETRIES}…")
                time.sleep(wait)
                continue

            return response

        except requests.exceptions.Timeout:
            wait = 5 * (attempt + 1)
            print(f"[downloader] Request timed out (attempt {attempt + 1}). "
                  f"Retrying in {wait} s…")
            time.sleep(wait)

        except requests.exceptions.ConnectionError as exc:
            wait = 5 * (attempt + 1)
            print(f"[downloader] Connection error: {exc}. "
                  f"Retrying in {wait} s…")
            time.sleep(wait)

    raise RuntimeError(
        f"[downloader] GET {url!r} failed after {MAX_RETRIES} attempts."
    )


def _post(url, **kwargs):
    """Wrapper around session.post() with timeout + exponential back-off retry."""
    kwargs.setdefault("timeout", (CONNECT_TIMEOUT, READ_TIMEOUT))
    kwargs.setdefault("headers", HEADERS)

    for attempt in range(MAX_RETRIES):
        try:
            response = session.post(url, **kwargs)

            if response.status_code in (429, 503):
                wait = (2 ** attempt) * 10
                print(f"[downloader] Rate limited ({response.status_code}). "
                      f"Waiting {wait} s before retry {attempt + 1}/{MAX_RETRIES}…")
                time.sleep(wait)
                continue

            return response

        except requests.exceptions.Timeout:
            wait = 5 * (attempt + 1)
            print(f"[downloader] POST timed out (attempt {attempt + 1}). "
                  f"Retrying in {wait} s…")
            time.sleep(wait)

        except requests.exceptions.ConnectionError as exc:
            wait = 5 * (attempt + 1)
            print(f"[downloader] Connection error: {exc}. "
                  f"Retrying in {wait} s…")
            time.sleep(wait)

    raise RuntimeError(
        f"[downloader] POST {url!r} failed after {MAX_RETRIES} attempts."
    )


class MixamoDownloader(QtCore.QObject):
    """Bulk download animations from Mixamo.

    Users can choose to download all animations in Mixamo (quite slow),
    only those that contain a specific word (faster), or just the T-Pose.

    The download mode is to be passed onto this class as an argument
    when creating an instance.

    The first step is to get the primary character ID and name.
    """

    # Create signals that will be used to emit info to the UI.
    finished = QtCore.Signal()
    total_tasks = QtCore.Signal(int)
    current_task = QtCore.Signal(int)

    # Initialize a counter for the progress bar.
    task = 1

    # Initialize a flag that tells the code to stop.
    stop = False

    def __init__(self, path, mode, query=None):
        """Initialize the Mixamo Downloader object.

        :param path: Output folder path
        :type path: str

        :param mode: Download mode ("all", "query" or "tpose")
        :type mode: str

        :param query: Keyword to be used as query when searching animations
        :type query: str
        """
        super().__init__()

        self.path = path
        self.mode = mode
        self.query = query

    def run(self):
        # Get the primary character ID and name.
        character_id = self.get_primary_character_id()
        character_name = self.get_primary_character_name()

        # If there's no character ID, it means that there was some problem
        # with the access token, so we better stop the code at this point.
        if not character_id:
            return

        # DOWNLOAD MODE: TPOSE
        if self.mode == "tpose":
            # The total amount of tasks to process is 1.
            self.total_tasks.emit(1)

            # Build the T-Pose payload.
            tpose_payload = self.build_tpose_payload(character_id, character_name)

            # Export and download the T-Pose.
            url = self.export_animation(character_id, tpose_payload)

            self.download_animation(url)

            # Emit the 'finished' signal to let the UI know that worker is done.
            self.finished.emit()
            return

        # DOWNLOAD MODE: ALL
        if self.mode == "all":
            # Get animation IDs from the JSON file on disk.
            anim_data = self.get_all_animations_data()

        # DOWNLOAD MODE: QUERY
        elif self.mode == "query":
            # Search for animation IDs according to the query entered by the user.
            anim_data = self.get_queried_animations_data(self.query)

        # The following code will be run for both the "all" and "query" modes.
        # Iterate the animation IDs and names dictionary.
        for anim_id, anim_name in anim_data.items():

            # Check if the 'Stop' button has been pressed in the UI.
            if self.stop:
                self.finished.emit()
                return

            # Skip animations that have already been downloaded.
            # We can do this check here — before any API calls — because
            # anim_name matches the file name that would be written to disk
            # (it is the same value later assigned to self.product_name inside
            # build_animation_payload).
            output_dir = self.path if self.path else os.getcwd()
            safe_anim_name = MixamoDownloader.sanitize_filename(anim_name)
            expected_file = os.path.join(output_dir, f"{safe_anim_name}.fbx")
            if os.path.isfile(expected_file):
                print(f"[downloader] Already exists, skipping: {safe_anim_name}.fbx")
                self.current_task.emit(self.task)
                self.task += 1
                continue

            # Hang-retry loop: if the export job times out (poll loop exhausted
            # MAX_POLL_ATTEMPTS without a "completed" status), we treat that as
            # a hang, wait an increasing backoff period, then re-submit the
            # export job and restart the poll loop from scratch.  This means
            # leaving the tool running overnight should eventually download
            # every animation even when Mixamo's servers are slow or flaky.
            downloaded = False
            for hang_attempt in range(MAX_HANG_RETRIES + 1):

                # Check stop flag at the start of every hang-retry too.
                if self.stop:
                    self.finished.emit()
                    return

                try:
                    # Build payload, export, poll, download.
                    anim_payload = self.build_animation_payload(character_id, anim_id)
                    url = self.export_animation(character_id, anim_payload)
                    self.download_animation(url)
                    downloaded = True
                    break  # success — move on to the next animation

                except RuntimeError as exc:
                    exc_msg = str(exc)

                    # Distinguish a hang (poll timeout) from a hard error
                    # (auth expiry, export job failed, etc.).
                    # export_animation raises "did not complete within" for
                    # poll timeouts and something else for hard failures.
                    is_hang = "did not complete within" in exc_msg

                    if is_hang and hang_attempt < MAX_HANG_RETRIES:
                        backoff = HANG_BACKOFF_BASE * (2 ** hang_attempt)
                        print(
                            f"[downloader] Hang detected for '{anim_name}' "
                            f"(attempt {hang_attempt + 1}/{MAX_HANG_RETRIES}). "
                            f"Waiting {backoff // 60} min {backoff % 60} s "
                            f"before retrying…"
                        )
                        # Sleep in small increments so the stop flag is still
                        # checked periodically during the long backoff wait.
                        elapsed = 0
                        while elapsed < backoff:
                            if self.stop:
                                self.finished.emit()
                                return
                            time.sleep(min(10, backoff - elapsed))
                            elapsed += 10
                        # Loop back and retry from build_animation_payload.

                    else:
                        # Hard error, or hang retries exhausted — log and skip.
                        if is_hang:
                            print(
                                f"[downloader] '{anim_name}' still hung after "
                                f"{MAX_HANG_RETRIES} retries. Skipping."
                            )
                        else:
                            print(f"[downloader] Skipping '{anim_name}': {exc_msg}")
                        break  # exit the hang-retry loop for this animation

            # Advance the progress counter whether we downloaded or skipped.
            if not downloaded:
                self.current_task.emit(self.task)
                self.task += 1

            # BUG 4 FIX: small delay between animations to avoid rapid-fire
            # requests that trigger Mixamo's rate limiter.
            time.sleep(INTER_DOWNLOAD_DELAY)

        # Emit the 'finished' signal to let the UI know that worker is done.
        self.finished.emit()
        return

    def get_primary_character_id(self):
        """Get the primary character ID (i.e: the one selected by the user).

        :return: Primary character ID
        :rtype: str
        """
        # BUG 1 FIX: use _get() wrapper (adds timeout + retry)
        response = _get("https://www.mixamo.com/api/v1/characters/primary")
        character_id = response.json().get("primary_character_id")
        return character_id

    def get_primary_character_name(self):
        """Get the primary character name (i.e: the one selected by the user).

        :return: Primary character name
        :rtype: str
        """
        # BUG 1 FIX: use _get() wrapper (adds timeout + retry)
        response = _get("https://www.mixamo.com/api/v1/characters/primary")
        character_name = response.json().get("primary_character_name")
        return character_name

    def build_tpose_payload(self, character_id, character_name):
        """Build the payload that will be used to export the T-Pose."""
        self.product_name = character_name

        payload = {
            "character_id": character_id,
            "product_name": self.product_name,
            "type": "Character",
            "preferences": {"format": "fbx7_2019", "mesh": "t-pose"},
            "gms_hash": None,
        }

        return json.dumps(payload)

    def get_queried_animations_data(self, query):
        """Get the ID and name of every animation found by the user query."""
        page_num = 1

        params = {
            "limit": 96,
            "page": page_num,
            "type": "Motion",
            "query": query,
        }

        # BUG 1 FIX: use _get() wrapper
        response = _get(
            "https://www.mixamo.com/api/v1/products",
            params=params,
        )

        data = response.json()
        num_pages = data["pagination"]["num_pages"]
        animations = []

        while page_num <= num_pages:
            params["page"] = page_num
            # BUG 1 FIX: use _get() wrapper
            response = _get(
                "https://www.mixamo.com/api/v1/products",
                params=params,
            )
            data = response.json()
            animations.extend(data["results"])
            page_num += 1

        anim_data = {}
        for animation in animations:
            anim_data[animation["id"]] = animation["description"]

        self.total_tasks.emit(len(anim_data))
        return anim_data

    def get_all_animations_data(self):
        """Get the ID and name of every animation in Mixamo from local JSON."""
        anim_data = {}
        with open("mixamo_anims.json", "r") as file:
            anim_data = json.load(file)

        self.total_tasks.emit(len(anim_data))
        return anim_data

    def build_animation_payload(self, character_id, anim_id):
        """Build the payload that will be used to export the animation."""
        # BUG 1 FIX: use _get() wrapper
        response = _get(
            f"https://www.mixamo.com/api/v1/products/{anim_id}"
            f"?similar=0&character_id={character_id}",
        )

        data = response.json()
        self.product_name = data["description"]
        _type = data["type"]

        preferences = {
            "format": "fbx7_2019",
            "skin": False,
            "fps": "24",
            "reducekf": "0",
        }

        gms_hash = data["details"]["gms_hash"]
        gms_hash_params = gms_hash["params"]
        param_values = [int(param[-1]) for param in gms_hash_params]
        params_string = ",".join(str(val) for val in param_values)

        gms_hash["params"] = params_string
        gms_hash["overdrive"] = 0

        trim_start = int(gms_hash["trim"][0])
        trim_end = int(gms_hash["trim"][1])
        gms_hash["trim"] = [trim_start, trim_end]

        payload = {
            "character_id": character_id,
            "product_name": self.product_name,
            "type": _type,
            "preferences": preferences,
            "gms_hash": [gms_hash],
        }

        return json.dumps(payload)

    def export_animation(self, character_id, payload):
        """Export the animation and retrieve the download link.

        BUG 3 FIX: the original while-loop had no exit condition other than
        status == "completed".  If Mixamo's monitor endpoint never returns
        "completed" (e.g. a stuck job after a rate-limit or auth expiry), the
        loop runs forever, freezing the QThread indefinitely.

        Fix: cap at MAX_POLL_ATTEMPTS and raise so the caller can skip this
        animation and continue the batch.
        """
        # BUG 1+2 FIX: use _post() wrapper
        _post(
            "https://www.mixamo.com/api/v1/animations/export",
            data=payload,
        )

        # BUG 3 FIX: capped poll loop — will not run forever
        for attempt in range(MAX_POLL_ATTEMPTS):
            time.sleep(POLL_INTERVAL)

            # BUG 1+2 FIX: use _get() wrapper
            response = _get(
                f"https://www.mixamo.com/api/v1/characters/{character_id}/monitor",
            )

            # BUG 5 FIX: detect auth expiry (session silently returns login
            # redirect or a non-JSON body after ~1 hour).
            if response.status_code in (401, 403):
                raise RuntimeError(
                    "Auth token expired mid-batch. "
                    "Please restart the tool and log in again."
                )

            try:
                data = response.json()
            except ValueError:
                # Non-JSON body — usually means session has expired.
                raise RuntimeError(
                    "Monitor endpoint returned non-JSON. "
                    "Session may have expired."
                )

            status = data.get("status")

            if status == "completed":
                return data.get("job_result")

            if status == "failed":
                raise RuntimeError(
                    f"Export job reported status 'failed' for '{self.product_name}'."
                )

        # If we reach here we exhausted MAX_POLL_ATTEMPTS without "completed".
        raise RuntimeError(
            f"Export job for '{self.product_name}' did not complete within "
            f"{MAX_POLL_ATTEMPTS * POLL_INTERVAL} seconds. Skipping."
        )

    @staticmethod
    def sanitize_filename(name):
        """Strip characters illegal in Windows filenames.

        Windows forbids: \ / : * ? " < > |
        A forward slash in an animation name like "Laying Down On An Exam
        Table/Bed As In A Doctors Office" would otherwise be treated as a
        directory separator, causing a FileNotFoundError.
        """
        for ch in ['\\', '/', ':', '*', '?', '"', '<', '>', '|']:
            name = name.replace(ch, "_")
        return name.strip()

    def download_animation(self, url):
        """Download the animation to disk."""
        if url:
            # BUG 1 FIX: use _get() wrapper (adds timeout + retry)
            response = _get(url)

            # Sanitize so illegal filename characters (e.g. "/" in
            # "Table/Bed") don't cause a FileNotFoundError on Windows.
            safe_name = self.sanitize_filename(self.product_name)

            if self.path:
                if not os.path.exists(self.path):
                    os.mkdir(self.path)
                open(os.path.join(self.path, f"{safe_name}.fbx"), "wb").write(
                    response.content
                )
            else:
                open(f"{safe_name}.fbx", "wb").write(response.content)

            self.current_task.emit(self.task)
            self.task += 1
