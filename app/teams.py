"""Teams web automation with Playwright (Python).

This is the unofficial part of desk-buddy: there is no public API for
joining a Teams call as a user client, so this drives the Teams web app
in a real Chromium window with a persistent browser profile (your Teams
sign-in persists in `.teams-profile`).

Design rules:
- Headful, never headless: the user must be able to see and, if needed,
  click through manually when the UI changes.
- Every click tries a list of selector candidates and logs a clear
  warning when none match, instead of crashing. The browser window stays
  open so manual fallback is always possible.
- Selector text lives in SELECTORS so a Teams UI change is a one-place fix.

Device selection (OBS Virtual Camera / CABLE Input) is attempted on the
pre-join screen but Teams renders those controls inconsistently across
versions; if auto-selection fails, the controller logs a warning and the
user picks the devices manually in the open browser window.
"""

import logging
import re
import time

log = logging.getLogger("desk-buddy.teams")

# Selector candidates, in try order. Teams web UI text changes over time;
# add new candidates here when a step stops matching.
SELECTORS = {
    # Pre-join screen: the button that enters the meeting.
    "join_now": [
        "button:has-text('Join now')",
        "button:has-text('Join')",
        "button[aria-label='Join now']",
        "button[aria-label='Join meeting']",
    ],
    # Pre-join device settings panel toggle.
    "device_settings": [
        "button[aria-label='Device settings']",
        "button:has-text('Device settings')",
        "button[title='Device settings']",
    ],
    # In-call mute / unmute toggle (aria-label flips with state).
    "mute_toggle": [
        "button[aria-label='Mute']",
        "button[aria-label='Unmute']",
        "button[title='Mute']",
        "button[title='Unmute']",
    ],
    # Leave / hang up.
    "leave": [
        "button[aria-label='Leave']",
        "button[aria-label='Hang up']",
        "button[title='Leave']",
    ],
    # Camera toggle (used only to verify the call screen loaded).
    "camera_toggle": [
        "button[aria-label='Turn camera on']",
        "button[aria-label='Turn camera off']",
    ],
}


class TeamsController:
    def __init__(self, config):
        self.profile_dir = config["teams"]["profile_dir"]
        self.join_timeout = config["teams"]["join_timeout_seconds"]
        self._playwright = None
        self._context = None
        self._page = None
        self.in_call = False

    # -- lifecycle -----------------------------------------------------
    def start(self):
        """Launch the persistent browser (headful). Safe to call twice."""
        if self._page is not None:
            return self._page
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        self._context = self._playwright.chromium.launch_persistent_context(
            self.profile_dir,
            headless=False,
            args=[
                "--use-fake-ui-for-media-stream",  # auto-allow mic/cam prompts
            ],
        )
        pages = self._context.pages
        self._page = pages[0] if pages else self._context.new_page()
        log.info("Teams browser started with profile %r", self.profile_dir)
        return self._page

    def close(self):
        try:
            if self._context is not None:
                self._context.close()
        finally:
            if self._playwright is not None:
                self._playwright.stop()
            self._page = None
            self._context = None
            self._playwright = None
            self.in_call = False

    # -- helpers -------------------------------------------------------
    def _click_first(self, candidates, timeout=5000):
        """Click the first matching selector; return True or log and return False."""
        for sel in candidates:
            try:
                self._page.locator(sel).first.click(timeout=timeout)
                log.info("clicked %r", sel)
                return True
            except Exception:  # noqa: BLE001 - try the next candidate
                continue
        log.warning("no selector matched: %s", candidates)
        return False

    def _select_device_option(self, wanted_substring):
        """In an open device-settings dropdown, click the option whose text
        contains `wanted_substring`. Returns True on success."""
        try:
            option = self._page.get_by_text(re.compile(re.escape(wanted_substring), re.I))
            option.first.click(timeout=3000)
            log.info("selected device option containing %r", wanted_substring)
            return True
        except Exception:  # noqa: BLE001 - caller logs the fallback
            return False

    def try_select_devices(self):
        """Best-effort device selection on the pre-join screen.

        Returns True only if both camera and mic were selected. On any
        failure, logs a manual-fallback warning and returns False — the
        user then picks OBS Virtual Camera / CABLE Input by hand in the
        still-open browser window.
        """
        if not self._click_first(SELECTORS["device_settings"], timeout=5000):
            log.warning(
                "could not open Teams device settings automatically; "
                "pick OBS Virtual Camera and CABLE Input manually in the browser window"
            )
            return False
        time.sleep(1)
        camera_ok = self._select_device_option("OBS Virtual Camera")
        mic_ok = self._select_device_option("CABLE Input")
        if not (camera_ok and mic_ok):
            log.warning(
                "could not auto-select devices (camera=%s mic=%s); "
                "pick OBS Virtual Camera and CABLE Input manually in the browser window",
                camera_ok,
                mic_ok,
            )
        return camera_ok and mic_ok

    # -- call control --------------------------------------------------
    def join(self, meeting_url):
        """Open a Teams meeting link and join. Returns True if the Join
        button was clicked; the caller should verify in-call state from
        the browser window if this returns False."""
        page = self.start()
        log.info("opening meeting URL %r", meeting_url)
        page.goto(meeting_url, timeout=60000)
        # Device selection happens on the pre-join screen, after navigation
        # and before clicking Join.
        self.try_select_devices()
        deadline = time.time() + self.join_timeout
        while time.time() < deadline:
            if self._click_first(SELECTORS["join_now"], timeout=3000):
                self.in_call = True
                log.info("joined meeting")
                return True
            # Still on a sign-in / lobby screen: wait and retry.
            time.sleep(3)
        log.error(
            "Join button never appeared within %ds — you may need to sign in "
            "or click Join manually in the browser window",
            self.join_timeout,
        )
        return False

    def set_muted(self, muted):
        """Set mute state. Returns True if the toggle ended in the wanted state."""
        if self._page is None:
            log.warning("set_muted called with no browser page")
            return False
        try:
            toggle = self._page.locator(SELECTORS["mute_toggle"][0]).first
            label = (toggle.get_attribute("aria-label") or "").lower()
            # aria-label shows the ACTION: "Mute" means currently unmuted.
            currently_muted = label == "unmute"
            if currently_muted == muted:
                return True
            toggle.click(timeout=5000)
            log.info("mute set to %s", muted)
            return True
        except Exception:  # noqa: BLE001 - fall back to any mute toggle candidate
            log.warning("mute toggle by aria-label failed, trying candidates")
            return self._click_first(SELECTORS["mute_toggle"], timeout=5000)

    def mute(self):
        return self.set_muted(True)

    def unmute(self):
        return self.set_muted(False)

    def leave(self):
        if self._page is None:
            return False
        ok = self._click_first(SELECTORS["leave"], timeout=5000)
        self.in_call = False
        return ok
