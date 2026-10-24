"""Audio device discovery helpers (Windows).

Teams audio routing in desk-buddy depends on two virtual devices:
- a loopback-style INPUT for capturing meeting audio (a device whose name
  contains "loopback", "Stereo Mix", or "What U Hear"), and
- an OUTPUT that Teams is listening to as its mic ("CABLE Input" from
  VB-Audio Cable).

These helpers find devices by substring so exact driver naming differences
do not break setup, and they always log what they found so the user can
correct config.json.
"""

import logging

log = logging.getLogger("desk-buddy.audio")


def list_devices():
    """Return a list of (index, name, kind) for all audio devices."""
    import sounddevice as sd

    devices = []
    for idx, dev in enumerate(sd.query_devices()):
        kind = []
        if dev["max_input_channels"] > 0:
            kind.append("input")
        if dev["max_output_channels"] > 0:
            kind.append("output")
        devices.append((idx, dev["name"], ",".join(kind)))
    return devices


def find_device(substrings, want_input=None, default=None):
    """Find the first device whose name contains any of `substrings`
    (case-insensitive). want_input True/False filters by direction; None
    accepts either. Returns the device index, or `default` if none match.
    """
    import sounddevice as sd

    needles = [s.lower() for s in substrings]
    for idx, dev in enumerate(sd.query_devices()):
        if want_input is True and dev["max_input_channels"] == 0:
            continue
        if want_input is False and dev["max_output_channels"] == 0:
            continue
        name = dev["name"].lower()
        if any(n in name for n in needles):
            log.info("audio device matched %r -> [%d] %s", substrings, idx, dev["name"])
            return idx
    log.warning("no audio device matched %r; using default %r", substrings, default)
    return default


def find_loopback_device(config):
    """Prefer a real loopback source; fall back to the default input."""
    idx = find_device(
        config["audio"]["loopback_device_contains"], want_input=True, default=None
    )
    if idx is not None:
        return idx
    import sounddevice as sd

    default = sd.default.device[0]
    log.warning("no loopback device found; using default input device %r", default)
    return default


def find_output_device(config):
    """Prefer the VB-Cable input; fall back to the default output."""
    idx = find_device(
        [config["audio"]["output_device_contains"]], want_input=False, default=None
    )
    if idx is not None:
        return idx
    import sounddevice as sd

    default = sd.default.device[1]
    log.warning("no VB-Cable output found; using default output device %r", default)
    return default
