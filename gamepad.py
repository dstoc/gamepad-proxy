#!/usr/bin/env python3
import os
import time
import traceback
from pathlib import Path
import argparse
from typing import List, Optional, Dict, Tuple, Any, Union, cast, Sequence

from evdev import InputDevice, ecodes, UInput
from evdev.device import AbsInfo

# ─────── GLOBAL VARS (set by command line) ───────
# Will be populated by parse_args()
ARGS: Optional[argparse.Namespace] = None

# ─────── ARGUMENT PARSING ───────
def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
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

def wait_for_device() -> InputDevice:
    """Block until the real gamepad appears and can be opened."""
    while True:
        if ARGS and os.path.exists(ARGS.device_link):
            try:
                dev = InputDevice(ARGS.device_link)
                print(f"✅ Opened real device: {dev.name}")
                return dev
            except Exception as e:
                print(f"⚠️ Could not open real device: {e}")
        time.sleep(1)


def extract_capabilities(dev: InputDevice) -> Dict[int, Union[List[int], List[Tuple[int, AbsInfo]]]]:
    """
    Extract device capabilities:
      - EV_KEY: list of button codes (ints)
      - EV_ABS: list of (code, AbsInfo)
      - EV_FF:  list of ff codes (ints)
    Returns a dict suitable for evdev.UInput.
    """
    raw: Dict[int, Any] = dev.capabilities(absinfo=True) # type: ignore
    caps: Dict[int, Union[List[int], List[Tuple[int, AbsInfo]]]] = {}

    # Keys
    caps[ecodes.EV_KEY] = raw.get(ecodes.EV_KEY, [])

    # Absolute axes
    abs_list: List[Tuple[int, AbsInfo]] = []
    # raw.get(ecodes.EV_ABS, []) can return List[int] or List[Tuple[int, AbsInfo]]
    # depending on whether absinfo was True or False in dev.capabilities()
    # if it's List[int], we need to call dev.absinfo() for each code
    for entry in raw.get(ecodes.EV_ABS, []):
        if isinstance(entry, tuple) and len(entry) == 2 and isinstance(entry[1], AbsInfo):
            code, info = entry[0], entry[1]
        else: # Should be an int if absinfo=False, but we called with absinfo=True
              # However, to be safe, and handle if dev.capabilities(absinfo=True) still returns codes for some reason
            code = entry if isinstance(entry, int) else entry[0] # type: ignore
            try:
                abs_info_val = dev.absinfo(code)
                if abs_info_val is not None: # absinfo can return None
                    info = abs_info_val
                else:
                    print(f"⚠️ Could not get absinfo for {code}, it was None.")
                    continue
            except Exception as e:
                print(f"⚠️ Could not get absinfo for {code}: {e}")
                continue
        abs_list.append((code, info))
    if abs_list:
        caps[ecodes.EV_ABS] = abs_list

    # Force feedback
    ff: List[int] = raw.get(ecodes.EV_FF, [])
    if ff:
        caps[ecodes.EV_FF] = ff

    print("DEBUG: extracted capabilities =", caps)
    return caps


def create_symlinks() -> bool:
    """
    Create /tmp/gamepad-event and /tmp/gamepad-js symlinks to the virtual device.
    """
    sys_input: str = '/sys/class/input'
    if ARGS is None:
        print("❌ ARGS not set, cannot create symlinks.")
        return False

    for entry in os.listdir(sys_input):
        if not entry.startswith('input'):
            continue
        name_file: str = os.path.join(sys_input, entry, 'name')
        try:
            with open(name_file) as f:
                name: str = f.read().strip()
        except FileNotFoundError:
            continue
        if name != ARGS.virtual_name:
            continue
        # Found virtual device: link its eventX and jsY
        for child in os.listdir(os.path.join(sys_input, entry)):
            src: str = ""
            dst: str = ""
            if child.startswith('event'):
                src, dst = f"/dev/input/{child}", ARGS.event_path
            elif child.startswith('js'):
                src, dst = f"/dev/input/{child}", ARGS.js_path
            else:
                continue
            if os.path.exists(src):
                # Create parent directory if it doesn't exist
                dst_dir = os.path.dirname(dst)
                if not os.path.exists(dst_dir):
                    os.makedirs(dst_dir)

                try:
                    if os.path.islink(dst) or os.path.exists(dst):
                        os.unlink(dst)
                except FileNotFoundError:
                    pass # This is fine, means it didn't exist
                except OSError as e:
                    print(f"Error removing existing symlink/file {dst}: {e}")
                    continue # Skip creating this symlink

                try:
                    os.symlink(src, dst)
                    print(f"🔗 {dst} → {src}")
                except OSError as e:
                    print(f"Error creating symlink from {src} to {dst}: {e}")

        return True # Found and processed the virtual device
    print(f"❌ Could not find {ARGS.virtual_name} to symlink")
    return False

# ─────── MAIN LOOP ───────

def run() -> None:
    print("🛠 Setting up virtual gamepad...")
    if ARGS is None:
        print("❌ ARGS not set, cannot run.")
        return

    # 1) Open the real device once, extract IDs…
    real: InputDevice = wait_for_device()
    caps: Dict[int, Union[List[int], List[Tuple[int, AbsInfo]]]] = extract_capabilities(real)
    # grab the original bus/vendor/product/version
    bus: int = real.info.bustype
    vendor: int = real.info.vendor
    product: int = real.info.product
    version: int = real.info.version
    real.close()

    # 2) Create the virtual device with matching IDs
    ui: UInput = UInput(
        cast(Optional[Dict[int, Sequence[int]]], caps),
        name=ARGS.virtual_name, # ARGS is checked at the start of run()
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
            dev: InputDevice = wait_for_device()
            dev.grab()
            print("▶️ Forwarding events...")
            for e in dev.read_loop():
                if e is not None: # read_loop can yield None
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

def main(cli_args: Optional[List[str]] = None) -> None:
    """
    Main function to setup and run the gamepad forwarder.
    Accepts cli_args for testing purposes.
    """
    global ARGS
    ARGS = parse_args(cli_args)
    run()

if __name__ == '__main__':
    main()
