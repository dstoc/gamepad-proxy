#!/usr/bin/env python3
import os
import time
import traceback
from pathlib import Path

from evdev import InputDevice, ecodes, UInput

# ─────── CONFIG ───────
DEVICE_LINK        = '/dev/input/by-id/usb-1038_SteelSeries_Stratus_Duo-event-joystick'
SYMLINK_EVENT_PATH = '/tmp/gamepad-event'
SYMLINK_JS_PATH    = '/tmp/gamepad-js'
VIRT_NAME          = 'VirtualGamepad'

# ─────── UTILITY FUNCTIONS ───────

def wait_for_device():
    """Block until the real gamepad appears and can be opened."""
    while True:
        if os.path.exists(DEVICE_LINK):
            try:
                dev = InputDevice(DEVICE_LINK)
                print(f"✅ Opened real device: {dev.name}")
                return dev
            except Exception as e:
                print(f"⚠️ Could not open real device: {e}")
        time.sleep(1)


def extract_capabilities(dev):
    """
    Extract device capabilities:
      - EV_KEY: list of button codes (ints)
      - EV_ABS: list of (code, AbsInfo)
      - EV_FF:  list of ff codes (ints)
    Returns a dict suitable for evdev.UInput.
    """
    raw = dev.capabilities()
    caps = {}

    # Keys
    caps[ecodes.EV_KEY] = raw.get(ecodes.EV_KEY, [])

    # Absolute axes
    abs_list = []
    for entry in raw.get(ecodes.EV_ABS, []):
        if isinstance(entry, tuple) and len(entry) == 2:
            code, info = entry
        else:
            code = entry
            try:
                info = dev.absinfo(code)
            except Exception as e:
                print(f"⚠️ Could not get absinfo for {code}: {e}")
                continue
        abs_list.append((code, info))
    if abs_list:
        caps[ecodes.EV_ABS] = abs_list

    # Force feedback
    ff = raw.get(ecodes.EV_FF, [])
    if ff:
        caps[ecodes.EV_FF] = ff

    print("DEBUG: extracted capabilities =", caps)
    return caps


def create_symlinks():
    """
    Create /tmp/gamepad-event and /tmp/gamepad-js symlinks to the virtual device.
    """
    sys_input = '/sys/class/input'
    for entry in os.listdir(sys_input):
        if not entry.startswith('input'):
            continue
        name_file = os.path.join(sys_input, entry, 'name')
        try:
            with open(name_file) as f:
                name = f.read().strip()
        except FileNotFoundError:
            continue
        if name != VIRT_NAME:
            continue
        # Found virtual device: link its eventX and jsY
        for child in os.listdir(os.path.join(sys_input, entry)):
            if child.startswith('event'):
                src, dst = f"/dev/input/{child}", SYMLINK_EVENT_PATH
            elif child.startswith('js'):
                src, dst = f"/dev/input/{child}", SYMLINK_JS_PATH
            else:
                continue
            if os.path.exists(src):
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                try:
                    os.unlink(dst)
                except FileNotFoundError:
                    pass
                os.symlink(src, dst)
                print(f"🔗 {dst} → {src}")
        return True
    print(f"❌ Could not find {VIRT_NAME} to symlink")
    return False

# ─────── MAIN LOOP ───────

def run():
    print("🛠 Setting up virtual gamepad...")

    # 1) Open the real device once, extract IDs…
    real = wait_for_device()
    caps = extract_capabilities(real)
    # grab the original bus/vendor/product/version
    bus, vendor, product, version = real.info.bustype, real.info.vendor, real.info.product, real.info.version
    real.close()

    # 2) Create the virtual device with matching IDs
    ui = UInput(
        caps,
        name=VIRT_NAME,
        bustype=bus,
        vendor=vendor,
        product=product,
        version=version
    )
    print("🎮 Virtual device created (IDs matched).")

    create_symlinks()

    # Forward loop
    while True:
        try:
            dev = wait_for_device()
            dev.grab()
            print("▶️ Forwarding events...")
            for e in dev.read_loop():
                print(f"DEBUG: incoming event - type={e.type}, code={e.code}, value={e.value}")
                ui.write(e.type, e.code, e.value)
                ui.syn()
        except (OSError, IOError) as ex:
            print(f"🔌 Disconnected: {ex}, waiting...")
            time.sleep(1)
        except Exception:
            print("💥 Unexpected error:")
            traceback.print_exc()
            time.sleep(1)

if __name__ == '__main__':
    run()
