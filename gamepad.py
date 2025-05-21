#!/usr/bin/env python3
import os
import time
import traceback
from pathlib import Path
import argparse

from evdev import InputDevice, ecodes, UInput

# ─────── GLOBAL VARS (set by command line) ───────
# Will be populated by parse_args()
ARGS = None

# ─────── ARGUMENT PARSING ───────
def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Gamepad Docker Binding Script")
    parser.add_argument('--device-link', type=str, default='/dev/input/by-id/usb-1038_SteelSeries_Stratus_Duo-event-joystick',
                        help='Path to the real gamepad device link')
    parser.add_argument('--event-path', type=str, default='/tmp/gamepad-event',
                        help='Desired path for the event symlink')
    parser.add_argument('--js-path', type=str, default='/tmp/gamepad-js',
                        help='Desired path for the joystick symlink')
    parser.add_argument('--virtual-name', type=str, default='VirtualGamepad',
                        help='Name for the virtual gamepad device')
    return parser.parse_args(argv)

# ─────── UTILITY FUNCTIONS ───────

def wait_for_device():
    """Block until the real gamepad appears and can be opened."""
    while True:
        if os.path.exists(ARGS.device_link):
            try:
                dev = InputDevice(ARGS.device_link)
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
        if name != ARGS.virtual_name:
            continue
        # Found virtual device: link its eventX and jsY
        for child in os.listdir(os.path.join(sys_input, entry)):
            if child.startswith('event'):
                src, dst = f"/dev/input/{child}", ARGS.event_path
            elif child.startswith('js'):
                src, dst = f"/dev/input/{child}", ARGS.js_path
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
    print(f"❌ Could not find {ARGS.virtual_name} to symlink")
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
        name=ARGS.virtual_name,
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

def main(cli_args=None):
    """
    Main function to setup and run the gamepad forwarder.
    Accepts cli_args for testing purposes.
    """
    global ARGS
    ARGS = parse_args(cli_args)
    run()

if __name__ == '__main__':
    main()
