import pytest
from gamepad import parse_args # Assuming gamepad.py is in the parent directory or PYTHONPATH is set
import subprocess
import time
import os
import errno # For error number constants
from evdev import UInput, ecodes, InputDevice, AbsInfo
from evdev.uinput import UInputError # Import UInputError
from pathlib import Path

# Unit tests for argument parsing (from previous successful runs)
def test_default_args():
    args = parse_args([])
    assert args.device_link == '/dev/input/by-id/usb-1038_SteelSeries_Stratus_Duo-event-joystick'
    assert args.event_path == '/tmp/gamepad-event'
    assert args.js_path == '/tmp/gamepad-js'
    assert args.virtual_name == 'VirtualGamepad'

def test_custom_device_link():
    custom_link = "/dev/input/my-custom-device"
    args = parse_args(["--device-link", custom_link])
    assert args.device_link == custom_link

def test_custom_event_path():
    custom_path = "/tmp/my-custom-event"
    args = parse_args(["--event-path", custom_path])
    assert args.event_path == custom_path

def test_custom_js_path():
    custom_path = "/tmp/my-custom-js"
    args = parse_args(["--js-path", custom_path])
    assert args.js_path == custom_path

def test_custom_virtual_name():
    custom_name = "MyCoolGamepad"
    args = parse_args(["--virtual-name", custom_name])
    assert args.virtual_name == custom_name

def test_all_custom_args():
    custom_link = "/dev/input/another-device"
    custom_event_path = "/opt/ev"
    custom_js_path = "/opt/js"
    custom_virtual_name = "SuperGamepad"
    args = parse_args([
        "--device-link", custom_link,
        "--event-path", custom_event_path,
        "--js-path", custom_js_path,
        "--virtual-name", custom_virtual_name
    ])
    assert args.device_link == custom_link
    assert args.event_path == custom_event_path
    assert args.js_path == custom_js_path
    assert args.virtual_name == custom_virtual_name

def test_unknown_argument():
    with pytest.raises(SystemExit):
        parse_args(["--unknown-arg", "value"])

def test_empty_custom_values():
    args = parse_args(["--device-link", "", "--event-path", "", "--js-path", "", "--virtual-name", ""])
    assert args.device_link == ""
    assert args.event_path == ""
    assert args.js_path == ""
    assert args.virtual_name == ""

# --- Integration Tests for Event Forwarding ---
CAPS = {
    ecodes.EV_KEY: [ecodes.BTN_A, ecodes.BTN_B],
    ecodes.EV_ABS: [(ecodes.ABS_X, AbsInfo(value=0, min=0, max=255, fuzz=0, flat=0, resolution=0))],
}
MOCK_REAL_DEVICE_NAME = "MockRealGamepadForTest"
GAMEPAD_SCRIPT_VIRTUAL_EVENT_SYMLINK = Path("/tmp/test_gamepad_script_virtual_event")
GAMEPAD_SCRIPT_VIRTUAL_JS_SYMLINK = Path("/tmp/test_gamepad_script_virtual_js")
GAMEPAD_SCRIPT_VIRTUAL_NAME = "TestVirtualGamepad"

@pytest.fixture(scope="module")
def mock_real_gamepad():
    ui_real = None # Define ui_real before try block for consistent access in finally
    try:
        print(f"Attempting to create mock real gamepad: {MOCK_REAL_DEVICE_NAME} with events: {CAPS}")
        ui_real = UInput(events=CAPS, name=MOCK_REAL_DEVICE_NAME, version=0x1)
        real_device_event_path = ui_real.device.path
        print(f"Mock real gamepad created at {real_device_event_path}")
        yield ui_real, real_device_event_path
    except UInputError as e:
        if "does not exist or is not a character device file" in str(e) or \
           "No such file or directory" in str(e): # Check for messages indicating /dev/uinput is missing/unusable
            pytest.skip(f"Skipping test: /dev/uinput is not available or uinput module not loaded ({e}).")
        else: # Other UInputError
            pytest.fail(f"Failed to create mock_real_gamepad due to UInputError: {e}")
    except (PermissionError, OSError) as e:
        if isinstance(e, OSError) and e.errno == errno.EACCES: # Specifically check for EACCES
            pytest.skip(f"Skipping test: Insufficient permissions for /dev/uinput (EACCES) ({e}). Configure udev rules or group membership.")
        # Re-raise if it's an OSError but not EACCES, or if it's a direct PermissionError not caught by EACCES logic (less likely for /dev/uinput)
        raise
    except Exception as e: # Catch any other unexpected exception during UInput creation
        pytest.fail(f"Failed to create mock_real_gamepad due to unexpected error: {e}")
    finally:
        print("Cleaning up mock real gamepad...")
        # Check if ui_real was successfully created and has a device before trying to close
        if ui_real and hasattr(ui_real, 'device') and ui_real.device: 
            ui_real.close()

@pytest.fixture(scope="module")
def gamepad_process(mock_real_gamepad): # Depends on the above fixture
    _, real_device_event_path = mock_real_gamepad
    
    if GAMEPAD_SCRIPT_VIRTUAL_EVENT_SYMLINK.exists():
        GAMEPAD_SCRIPT_VIRTUAL_EVENT_SYMLINK.unlink(missing_ok=True)
    if GAMEPAD_SCRIPT_VIRTUAL_JS_SYMLINK.exists():
        GAMEPAD_SCRIPT_VIRTUAL_JS_SYMLINK.unlink(missing_ok=True)

    script_path = Path(__file__).parent.parent / "gamepad.py"
    if not script_path.exists():
        pytest.fail(f"gamepad.py script not found at {script_path}")

    args_list = [
        "python3", str(script_path),
        "--device-link", real_device_event_path, 
        "--event-path", str(GAMEPAD_SCRIPT_VIRTUAL_EVENT_SYMLINK),
        "--js-path", str(GAMEPAD_SCRIPT_VIRTUAL_JS_SYMLINK),
        "--virtual-name", GAMEPAD_SCRIPT_VIRTUAL_NAME
    ]
    
    proc = None
    try:
        print(f"Starting gamepad.py with args: {' '.join(args_list)}")
        proc = subprocess.Popen(args_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        max_wait = 15
        start_time = time.time()
        symlink_created = False
        while time.time() - start_time < max_wait:
            if GAMEPAD_SCRIPT_VIRTUAL_EVENT_SYMLINK.exists():
                time.sleep(0.5) 
                symlink_created = True
                break
            if proc.poll() is not None:
                 stdout, stderr = proc.communicate()
                 print(f"gamepad.py terminated prematurely. Stdout: {stdout.decode(errors='ignore')}, Stderr: {stderr.decode(errors='ignore')}")
                 pytest.fail("gamepad.py terminated prematurely during startup.")
            time.sleep(0.1)
        
        if not symlink_created:
            stdout, stderr = proc.communicate()
            print(f"gamepad.py stdout: {stdout.decode(errors='ignore')}")
            print(f"gamepad.py stderr: {stderr.decode(errors='ignore')}")
            pytest.fail(f"Timeout waiting for gamepad.py to create symlink: {GAMEPAD_SCRIPT_VIRTUAL_EVENT_SYMLINK}")

        print(f"gamepad.py started and symlink {GAMEPAD_SCRIPT_VIRTUAL_EVENT_SYMLINK} found.")
        yield proc
    finally:
        if proc:
            print("Terminating gamepad.py process...")
            proc.terminate()
            try:
                stdout, stderr = proc.communicate(timeout=5)
                print(f"gamepad.py exited. Stdout: {stdout.decode(errors='ignore')}, Stderr: {stderr.decode(errors='ignore')}")
            except subprocess.TimeoutExpired:
                print("gamepad.py did not terminate gracefully, killing.")
                proc.kill()
                stdout, stderr = proc.communicate()
                print(f"gamepad.py killed. Stdout: {stdout.decode(errors='ignore')}, Stderr: {stderr.decode(errors='ignore')}")

        if GAMEPAD_SCRIPT_VIRTUAL_EVENT_SYMLINK.exists():
            GAMEPAD_SCRIPT_VIRTUAL_EVENT_SYMLINK.unlink(missing_ok=True)
        if GAMEPAD_SCRIPT_VIRTUAL_JS_SYMLINK.exists():
            GAMEPAD_SCRIPT_VIRTUAL_JS_SYMLINK.unlink(missing_ok=True)

def test_event_forwarding(mock_real_gamepad, gamepad_process):
    ui_real, _ = mock_real_gamepad
    time.sleep(2) 

    dev_virtual = None
    try:
        retries = 10
        for i in range(retries):
            try:
                dev_virtual = InputDevice(str(GAMEPAD_SCRIPT_VIRTUAL_EVENT_SYMLINK))
                print(f"Successfully opened gamepad.py's virtual device: {dev_virtual.name} (attempt {i+1})")
                break
            except Exception as e:
                print(f"Attempt {i+1} to open virtual device failed: {e}")
                if i < retries - 1:
                    time.sleep(0.5 + i * 0.1)
                else:
                    pytest.fail(f"Could not open gamepad.py's virtual device at {GAMEPAD_SCRIPT_VIRTUAL_EVENT_SYMLINK} after multiple retries: {e}")
        if dev_virtual is None:
             pytest.fail(f"dev_virtual is None after retry loop for {GAMEPAD_SCRIPT_VIRTUAL_EVENT_SYMLINK}")
    except Exception as e:
        pytest.fail(f"Failed to open gamepad.py's virtual device: {e}")

    events_to_send = [
        {'type': ecodes.EV_KEY, 'code': ecodes.BTN_A, 'value': 1},
        {'type': ecodes.EV_KEY, 'code': ecodes.BTN_A, 'value': 0},
        {'type': ecodes.EV_ABS, 'code': ecodes.ABS_X, 'value': 128},
    ]

    for event_spec in events_to_send:
        print(f"Sending event to mock real device: type={event_spec['type']}, code={event_spec['code']}, value={event_spec['value']}")
        ui_real.write(event_spec['type'], event_spec['code'], event_spec['value'])
        ui_real.syn()
        time.sleep(0.2)

    events_received = []
    import select
    fd = dev_virtual.fd
    
    dev_virtual.grab()
    read_duration = 2.0
    end_time = time.time() + read_duration
    
    while time.time() < end_time:
        ready, _, _ = select.select([fd], [], [], 0.1)
        if not ready:
            continue
        try:
            for event in dev_virtual.read():
                print(f"Received event from gamepad.py's virtual device: type={event.type}, code={event.code}, value={event.value}")
                events_received.append((event.type, event.code, event.value))
        except BlockingIOError:
            continue
        except Exception as e:
            print(f"Error reading from virtual device: {e}")
            break

    dev_virtual.ungrab()
    dev_virtual.close()

    print(f"Raw events received: {events_received}")
    filtered_events_received = [
        e for e in events_received 
        if e[0] != ecodes.EV_SYN and not (e[0] == ecodes.EV_MSC and e[1] == ecodes.MSC_SCAN)
    ]
    print(f"Filtered events received: {filtered_events_received}")

    expected_core_events_tuples = [
        (ecodes.EV_KEY, ecodes.BTN_A, 1),
        (ecodes.EV_KEY, ecodes.BTN_A, 0),
        (ecodes.EV_ABS, ecodes.ABS_X, 128),
    ]

    missing_events = [e for e in expected_core_events_tuples if e not in filtered_events_received]
    if missing_events:
        pytest.fail(f"Missing expected core events: {missing_events}. Received (filtered): {filtered_events_received}")

    assert len(filtered_events_received) == len(expected_core_events_tuples), \
        f"Expected {len(expected_core_events_tuples)} core events, but got {len(filtered_events_received)} (after filtering SYN/MSC)"
