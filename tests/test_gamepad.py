import pytest
from gamepad import parse_args # Assuming gamepad.py is in the parent directory or PYTHONPATH is set

def test_default_args():
    """Tests that default arguments are set correctly when no command-line arguments are provided."""
    args = parse_args([])
    assert args.device_link == '/dev/input/by-id/usb-1038_SteelSeries_Stratus_Duo-event-joystick'
    assert args.event_path == '/tmp/gamepad-event'
    assert args.js_path == '/tmp/gamepad-js'
    assert args.virtual_name == 'VirtualGamepad'

def test_custom_device_link():
    """Tests that a custom device link is correctly parsed."""
    custom_link = "/dev/input/my-custom-device"
    args = parse_args(["--device-link", custom_link])
    assert args.device_link == custom_link
    # Check that other args remain default
    assert args.event_path == '/tmp/gamepad-event'
    assert args.js_path == '/tmp/gamepad-js'
    assert args.virtual_name == 'VirtualGamepad'

def test_custom_event_path():
    """Tests that a custom event path is correctly parsed."""
    custom_path = "/tmp/my-custom-event"
    args = parse_args(["--event-path", custom_path])
    assert args.event_path == custom_path
    # Check that other args remain default
    assert args.device_link == '/dev/input/by-id/usb-1038_SteelSeries_Stratus_Duo-event-joystick'
    assert args.js_path == '/tmp/gamepad-js'
    assert args.virtual_name == 'VirtualGamepad'

def test_custom_js_path():
    """Tests that a custom JS path is correctly parsed."""
    custom_path = "/tmp/my-custom-js"
    args = parse_args(["--js-path", custom_path])
    assert args.js_path == custom_path
    # Check that other args remain default
    assert args.device_link == '/dev/input/by-id/usb-1038_SteelSeries_Stratus_Duo-event-joystick'
    assert args.event_path == '/tmp/gamepad-event'
    assert args.virtual_name == 'VirtualGamepad'

def test_custom_virtual_name():
    """Tests that a custom virtual name is correctly parsed."""
    custom_name = "MyCoolGamepad"
    args = parse_args(["--virtual-name", custom_name])
    assert args.virtual_name == custom_name
    # Check that other args remain default
    assert args.device_link == '/dev/input/by-id/usb-1038_SteelSeries_Stratus_Duo-event-joystick'
    assert args.event_path == '/tmp/gamepad-event'
    assert args.js_path == '/tmp/gamepad-js'

def test_all_custom_args():
    """Tests that all arguments are correctly parsed when provided."""
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

# Example of how you might test for an unknown argument, expecting a SystemExit
def test_unknown_argument():
    """Tests that providing an unknown argument causes the parser to exit."""
    with pytest.raises(SystemExit):
        parse_args(["--unknown-arg", "value"])

def test_empty_custom_values():
    """Tests providing empty strings as custom values (argparse should handle them as strings)."""
    args = parse_args([
        "--device-link", "",
        "--event-path", "",
        "--js-path", "",
        "--virtual-name", ""
    ])
    assert args.device_link == ""
    assert args.event_path == ""
    assert args.js_path == ""
    assert args.virtual_name == ""

# --- Integration Tests for Event Forwarding ---

import subprocess
import time
import os
from evdev import UInput, ecodes, InputDevice, AbsInfo
from pathlib import Path
import threading # Not strictly needed if using subprocess and select

# Capabilities for our mock real device and the virtual device gamepad.py will create
CAPS = {
    ecodes.EV_KEY: [ecodes.BTN_A, ecodes.BTN_B],
    ecodes.EV_ABS: [(ecodes.ABS_X, AbsInfo(value=0, min=0, max=255, fuzz=0, flat=0, resolution=0))],
}
MOCK_REAL_DEVICE_NAME = "MockRealGamepadForTest"
# No symlink dir for mock real device, pass direct path.

GAMEPAD_SCRIPT_VIRTUAL_EVENT_SYMLINK = Path("/tmp/test_gamepad_script_virtual_event")
GAMEPAD_SCRIPT_VIRTUAL_JS_SYMLINK = Path("/tmp/test_gamepad_script_virtual_js")
GAMEPAD_SCRIPT_VIRTUAL_NAME = "TestVirtualGamepad"


@pytest.fixture(scope="module")
def mock_real_gamepad():
    # This fixture might require sudo to run UInput
    if os.geteuid() != 0:
        pytest.skip("mock_real_gamepad fixture requires root privileges for UInput.")

    ui_real = None
    try:
        print(f"Attempting to create mock real gamepad: {MOCK_REAL_DEVICE_NAME} with caps: {CAPS}")
        ui_real = UInput(capabilities=CAPS, name=MOCK_REAL_DEVICE_NAME, version=0x1)
        real_device_event_path = ui_real.device.path
        print(f"Mock real gamepad created at {real_device_event_path}")
        yield ui_real, real_device_event_path # Provide the UInput object and its direct event path
    except Exception as e:
        pytest.fail(f"Failed to create mock_real_gamepad: {e}")
    finally:
        if ui_real:
            print("Cleaning up mock real gamepad...")
            ui_real.close()


@pytest.fixture(scope="module")
def gamepad_process(mock_real_gamepad): # Depends on the above fixture
    _, real_device_event_path = mock_real_gamepad # Get the path from the fixture
    
    # Ensure symlinks that gamepad.py will create are clean
    if GAMEPAD_SCRIPT_VIRTUAL_EVENT_SYMLINK.exists():
        GAMEPAD_SCRIPT_VIRTUAL_EVENT_SYMLINK.unlink(missing_ok=True)
    if GAMEPAD_SCRIPT_VIRTUAL_JS_SYMLINK.exists():
        GAMEPAD_SCRIPT_VIRTUAL_JS_SYMLINK.unlink(missing_ok=True)

    # Path to the gamepad.py script, assuming it's in the parent directory of tests/
    script_path = Path(__file__).parent.parent / "gamepad.py"
    if not script_path.exists():
        pytest.fail(f"gamepad.py script not found at {script_path}")

    args = [
        "python3", str(script_path),
        "--device-link", real_device_event_path, 
        "--event-path", str(GAMEPAD_SCRIPT_VIRTUAL_EVENT_SYMLINK),
        "--js-path", str(GAMEPAD_SCRIPT_VIRTUAL_JS_SYMLINK),
        "--virtual-name", GAMEPAD_SCRIPT_VIRTUAL_NAME
    ]
    
    proc = None
    try:
        print(f"Starting gamepad.py with args: {' '.join(args)}")
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        max_wait = 15 # Increased timeout
        start_time = time.time()
        symlink_created = False
        while time.time() - start_time < max_wait:
            if GAMEPAD_SCRIPT_VIRTUAL_EVENT_SYMLINK.exists():
                # Check if it's a valid symlink and points to a device
                # This is a bit tricky as the /dev/input/eventX node for the virtual device also takes time
                time.sleep(0.5) # Give a bit more time for the actual device node to be ready
                symlink_created = True
                break
            if proc.poll() is not None: # Process terminated
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
        yield proc # Yield the process so the test can use it if needed, though it runs in background
    
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
    if os.geteuid() != 0:
        pytest.skip("This test requires root privileges for UInput by both test and script.")

    ui_real, _ = mock_real_gamepad # UInput object for the mock real device
    
    # gamepad_process fixture ensures the process is running and symlink is created.
    # Wait a bit more to ensure gamepad.py's internal virtual device is fully ready.
    time.sleep(2) # Increased sleep

    dev_virtual = None
    try:
        retries = 10 # Increased retries
        for i in range(retries):
            try:
                dev_virtual = InputDevice(str(GAMEPAD_SCRIPT_VIRTUAL_EVENT_SYMLINK))
                print(f"Successfully opened gamepad.py's virtual device: {dev_virtual.name} (attempt {i+1})")
                break
            except Exception as e:
                print(f"Attempt to open virtual device failed: {e}, retries left: {retries-1-i}")
                if i < retries - 1:
                    time.sleep(0.5 + i * 0.1) # Exponential backoff-like delay
                else:
                    pytest.fail(f"Could not open gamepad.py's virtual device at {GAMEPAD_SCRIPT_VIRTUAL_EVENT_SYMLINK} after multiple retries: {e}")
        if dev_virtual is None: # Should be caught by the fail above, but as a safeguard
             pytest.fail(f"dev_virtual is None after retry loop for {GAMEPAD_SCRIPT_VIRTUAL_EVENT_SYMLINK}")

    except Exception as e: # Catch any other unexpected error during setup
        pytest.fail(f"Failed to open gamepad.py's virtual device: {e}")

    events_to_send = [
        {'type': ecodes.EV_KEY, 'code': ecodes.BTN_A, 'value': 1},  # Button A press
        {'type': ecodes.EV_KEY, 'code': ecodes.BTN_A, 'value': 0},  # Button A release
        {'type': ecodes.EV_ABS, 'code': ecodes.ABS_X, 'value': 128}, # ABS_X movement
    ]

    for event_spec in events_to_send:
        print(f"Sending event to mock real device: type={event_spec['type']}, code={event_spec['code']}, value={event_spec['value']}")
        ui_real.write(event_spec['type'], event_spec['code'], event_spec['value'])
        ui_real.syn()
        time.sleep(0.2) # Give a bit of time for event propagation

    events_received = []
    import select
    fd = dev_virtual.fd
    
    # Try to read the events we expect (plus potential SYN_REPORTs and MSC_SCANs)
    # Each event sent results in the event itself + a SYN_REPORT.
    # Key presses might also generate MSC_SCAN.
    # BTN_A press: EV_KEY, EV_MSC (maybe), EV_SYN
    # BTN_A release: EV_KEY, EV_MSC (maybe), EV_SYN
    # ABS_X: EV_ABS, EV_SYN
    # Max events to read: 3 data events * (1 data + 1 MSC_SCAN + 1 SYN) = 9, roughly.
    # Read for a limited time or number of events
    
    dev_virtual.grab() # Grab to ensure we get events
    
    # Adjusting read loop: read for a certain duration to collect events
    read_duration = 2.0 # seconds
    end_time = time.time() + read_duration
    
    while time.time() < end_time:
        ready, _, _ = select.select([fd], [], [], 0.1) # 0.1 second timeout for select
        if not ready:
            continue # No event, continue to check time
        
        try:
            for event in dev_virtual.read(): # read() should yield available events
                print(f"Received event from gamepad.py's virtual device: type={event.type}, code={event.code}, value={event.value}")
                events_received.append((event.type, event.code, event.value))
        except BlockingIOError: # If fd is non-blocking and no events
            continue
        except Exception as e:
            print(f"Error reading from virtual device: {e}")
            break # Stop reading on error

    dev_virtual.ungrab()
    dev_virtual.close()

    print(f"Raw events received: {events_received}")

    # Filter out SYN_REPORT events and MSC_SCAN for this basic check.
    # The goal is to see if the core data events we sent are present.
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

    # Check if all expected core events are present in the filtered list
    missing_events = []
    for expected_event in expected_core_events_tuples:
        if expected_event not in filtered_events_received:
            missing_events.append(expected_event)
    
    if missing_events:
        pytest.fail(f"Missing expected core events: {missing_events}. Received (filtered): {filtered_events_received}")

    # Additionally, check that no unexpected core events were received.
    # This means filtered_events_received should ideally be a permutation of expected_core_events_tuples.
    # For simplicity, we'll check if the lengths match. If more events are present, they are unexpected.
    assert len(filtered_events_received) == len(expected_core_events_tuples), \
        f"Expected {len(expected_core_events_tuples)} core events, but got {len(filtered_events_received)} (after filtering SYN/MSC)"

