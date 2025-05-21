# Testing Strategy for Gamepad Docker Binding

This document outlines the strategy for testing the `gamepad.py` script, which uses `evdev` and `UInput` to manage gamepad devices in a Docker environment.

## 1. Overview

Testing will be divided into unit tests and integration tests. `pytest` is recommended as the test runner, along with `unittest.mock` for mocking.

Given the nature of `evdev` and `UInput`, many tests will be Linux-specific and some integration tests may require elevated privileges (root or specific udev rules) to create virtual input devices.

## 2. Unit Tests

Unit tests will focus on testing individual functions and components in isolation.

*   **Argument Parsing (`gamepad.py` `if __name__ == '__main__':`)**
    *   **Objective:** Verify that command-line arguments are parsed correctly and default values are applied.
    *   **Method:**
        *   Use `unittest.mock.patch` to mock `sys.argv`.
        *   Call the argument parsing setup.
        *   Assert that the `ARGS` global variable (or the direct output of `parser.parse_args()`) contains the expected values for various combinations of provided and omitted arguments.

*   **Capability Extraction (`extract_capabilities`)**
    *   **Objective:** Ensure device capabilities are correctly extracted.
    *   **Method:**
        *   Create a mock `evdev.InputDevice` object.
        *   Populate its `capabilities()` method to return a predefined dictionary of capabilities (including `EV_KEY`, `EV_ABS`, `EV_FF`).
        *   Populate its `absinfo()` method if `EV_ABS` codes are returned by `capabilities()`.
        *   Call `extract_capabilities` with the mock device.
        *   Assert that the returned dictionary matches the expected structure for `UInput`.

*   **Symlink Creation (`create_symlinks`)**
    *   **Objective:** Verify that symlinks are created correctly and point to the expected virtual device nodes.
    *   **Method:** This leans towards an integration test due to reliance on `/sys/class/input` and `/dev/input` structures created by a virtual device. However, some aspects could be unit-tested with extensive mocking.
        *   **Mocking `os.listdir`, `os.path.join`, `open`, `os.path.exists`, `os.makedirs`, `os.unlink`, `os.symlink`**:
            *   Simulate the directory structure of `/sys/class/input` and the presence of a virtual device with a specific name (`ARGS.virtual_name`).
            *   Mock `open` to return a file-like object that yields the virtual device name when read.
            *   Verify that `os.symlink` is called with the correct source and destination paths based on `ARGS.event_path` and `ARGS.js_path`.
            *   This is complex to mock accurately. A more practical approach is covered in Integration Tests.

## 3. Integration Tests

Integration tests will verify the interaction between different parts of the script and the system. These tests will likely require root privileges or appropriate udev rules to allow `UInput` device creation.

*   **Core Event Forwarding**
    *   **Objective:** Test that events from a simulated "real" gamepad are correctly forwarded to the virtual gamepad created by `gamepad.py`.
    *   **Method:**
        1.  **Test Setup:**
            *   Create a "mock real gamepad" using `evdev.UInput`. This mock device will simulate the actual gamepad hardware. Configure it with specific capabilities (e.g., a few buttons and axes).
            *   The path to this "mock real gamepad" (e.g., `/dev/input/eventXX`) will be passed to `gamepad.py` via the `--device-link` argument.
            *   The test script will need to listen to the virtual gamepad created by `gamepad.py`. The symlinks (`ARGS.event_path`, `ARGS.js_path`) created by `gamepad.py` should point to this virtual device. The test can open this device using `evdev.InputDevice(ARGS.event_path)`.
        2.  **Execution:**
            *   Run `gamepad.py` in a separate thread or process, configured to use the "mock real gamepad".
            *   The main test thread writes events (e.g., button presses, axis movements) to the "mock real gamepad" using its `UInput.write()` and `UInput.syn()` methods.
        3.  **Verification:**
            *   The test thread reads events from the virtual gamepad (created by `gamepad.py`) via the symlink.
            *   Assert that the events read from the virtual gamepad match the events written to the "mock real gamepad".

*   **Symlink Management**
    *   **Objective:** Verify that symlinks are created, updated, and point to the correct device nodes.
    *   **Method:**
        1.  **Setup:** Start `gamepad.py` with a "mock real gamepad" as in the core event forwarding test.
        2.  **Verification:**
            *   After `gamepad.py` has initialized, use `os.path.exists()`, `os.path.islink()`, and `os.readlink()` to verify:
                *   `ARGS.event_path` and `ARGS.js_path` exist and are symlinks.
                *   They point to device nodes under `/dev/input/` that correspond to the virtual gamepad created by `gamepad.py` (identified by `ARGS.virtual_name` in `/sys/class/input/.../name`).

*   **Device Reconnection Logic**
    *   **Objective:** Test the script's ability to handle disconnections and reconnections of the real gamepad.
    *   **Method:**
        1.  **Initial Connection:**
            *   Start with the "mock real gamepad" (created via `UInput`) available.
            *   Run `gamepad.py`. Verify event forwarding is working.
        2.  **Simulate Disconnection:**
            *   Close the "mock real gamepad" (call `close()` on its `UInput` object). This should cause `gamepad.py`'s `dev.read_loop()` or `dev.grab()` to raise an `OSError`.
            *   Verify (e.g., by checking logs or internal state if possible) that `gamepad.py` detects the disconnection and enters the `wait_for_device()` loop.
            *   During this time, no events should be forwarded. The virtual device created by `gamepad.py` should remain, but receive no new events.
        3.  **Simulate Reconnection:**
            *   Recreate the "mock real gamepad" (a new `UInput` instance, or make the original path accessible again if that's how it's simulated) with the same device path that `gamepad.py` is polling.
            *   Verify that `gamepad.py` successfully reopens the device.
        4.  **Verify Operation:**
            *   Send new events to the "mock real gamepad".
            *   Verify that these events are once again forwarded to the virtual gamepad.

## 4. Tools and Libraries

*   **Test Runner:** `pytest`
*   **Mocking:** `unittest.mock` (part of Python's standard library) for mocking objects and functions.
*   **`evdev` library:** Essential for creating mock `UInput` devices and interacting with `InputDevice`.

## 5. Considerations

*   **Root Privileges:**
    *   Creating `UInput` devices (both for the "mock real gamepad" and by `gamepad.py` itself) typically requires root privileges or specific udev rules that grant access to `/dev/uinput`.
    *   Tests requiring these privileges should be clearly marked.
    *   Consider using `pytest.mark.skipif` to skip these tests if not running as root or if `/dev/uinput` is not writable.
    *   Alternatively, these tests could be designed to run in a Docker container where root access is available and the necessary device nodes can be managed.
*   **Platform Specificity:** These tests are inherently Linux-specific due to the reliance on `evdev` and the `/dev/input` system. They will not run on Windows or macOS.
*   **Timing and Asynchronicity:**
    *   The script involves loops and waiting for devices. Tests, especially for reconnection, will need to manage timing carefully (e.g., `time.sleep()` or more sophisticated synchronization primitives if running `gamepad.py` in a thread).
*   **Clean Up:** Ensure that any mock devices or symlinks created during tests are properly cleaned up, even if tests fail. `pytest` fixtures (`yield` fixtures) can be helpful here.
*   **Logging:** Enhancing `gamepad.py` with more detailed logging (e.g., using the `logging` module) can aid debugging and make it easier to verify behavior in tests by inspecting log output.

## 6. Test Structure (Example with pytest)

```python
# tests/test_gamepad.py
import pytest
from unittest.mock import patch, MagicMock
from evdev import UInput, ecodes

# Example for argument parsing
def test_parse_args_defaults():
    # ... setup mock sys.argv ...
    # ... run parsing logic ...
    # ... assert ARGS ...
    pass

@pytest.mark.require_root # Custom marker
def test_event_forwarding():
    # 1. Create mock_real_gamepad (UInput)
    # 2. Start gamepad.py in a thread (with args pointing to mock_real_gamepad)
    # 3. Create listener for gamepad.py's virtual device (InputDevice on symlink)
    # 4. Write events to mock_real_gamepad
    # 5. Read and assert events from the listener
    # 6. Cleanup
    pass

@pytest.mark.require_root
def test_reconnection():
    # 1. Setup as above
    # 2. Simulate disconnect (close mock_real_gamepad)
    # 3. Verify gamepad.py is waiting (e.g., check logs, or try to send event - should not pass)
    # 4. Simulate reconnect (recreate mock_real_gamepad)
    # 5. Verify forwarding resumes
    # 6. Cleanup
    pass

# Conftest.py for root check
# content of conftest.py
import pytest
import os

def pytest_configure(config):
    config.addinivalue_line(
        "markers", "require_root: mark test as requiring root privileges"
    )

def pytest_runtest_setup(item):
    if item.get_closest_marker("require_root"):
        if os.geteuid() != 0: # Check if not root
            pytest.skip("Test requires root privileges")

```

This detailed plan should provide a solid foundation for developing comprehensive tests for the `gamepad.py` script.

## 7. Practical Implementation Notes

This section details findings and learnings from the initial implementation of unit and integration tests for `gamepad.py`.

*   **Unit Testing `argparse`**:
    *   Refactoring the argument parsing logic into a dedicated `parse_args(argv=None)` function within `gamepad.py` proved highly effective for unit testing.
    *   `pytest` was used to invoke this function with various lists of arguments (simulating `sys.argv`) and assert the correctness of the parsed `argparse.Namespace` object. This covered default values, custom inputs for each argument, and error cases like unknown arguments (which correctly raised `SystemExit`).

*   **Integration Testing Event Forwarding**:
    *   **Mock "Real" Device:** Using `evdev.UInput` to create a "mock real gamepad" within the test environment was successful. This allowed the test to have full control over the capabilities and events of the device that `gamepad.py` attempts to read from.
    *   **Process and Fixture Management:**
        *   `gamepad.py` was run as a separate process using the `subprocess` module.
        *   `pytest` fixtures were instrumental in managing the lifecycle of both the "mock real gamepad" (`UInput` instance) and the `gamepad.py` subprocess. Module-scoped fixtures (`scope="module"`) were used to set up these resources once per test module run, improving efficiency.
        *   The fixtures handled setup (creating the mock device, cleaning old symlinks, starting the process) and teardown (closing the mock device, terminating the process, removing test symlinks).
    *   **Root Privileges:** Tests involving `evdev.UInput` (both for creating the "mock real gamepad" and for `gamepad.py` itself to create its virtual device) require root privileges. This was handled by checking `os.geteuid() != 0` at the beginning of the relevant fixtures and test functions, and using `pytest.skip()` to gracefully skip these tests if not run as root. This prevents test failures due to permission errors and makes the test suite runnable in restricted environments (albeit with some tests skipped).
    *   **Timing Considerations:**
        *   Several `time.sleep()` calls and explicit wait loops were necessary:
            *   Waiting for the `gamepad.py` subprocess to create its symlinks after startup. A loop with a timeout was implemented in the `gamepad_process` fixture.
            *   Waiting briefly after sending an event from the "mock real gamepad" to allow time for `gamepad.py` to process and forward it.
            *   A retry loop with increasing delays was added when opening the virtual device created by `gamepad.py` via its symlink, as there can be a slight delay between symlink creation and the underlying event node becoming fully available for `InputDevice()`.
        *   Using `select.select()` for reading events from the virtual device provided non-blocking reads with a timeout, crucial for preventing tests from hanging if events are not received as expected.
    *   **`--device-link` Usage:** For the integration test, `gamepad.py`'s `--device-link` argument was successfully used with the direct event path of the mock `UInput` device (e.g., `/dev/input/eventX`). While `gamepad.py` is often used with symlinks (like those in `/dev/input/by-id/`), its `wait_for_device()` function directly uses `os.path.exists()` and `InputDevice()` on the provided path, making it compatible with direct event device paths as well. This simplifies the test setup as the test doesn't need to create an additional symlink for the mock real device.
    *   **Core Functionality Confirmed:** The core event forwarding mechanism (reading from one device, extracting capabilities, creating a new virtual device, and writing events to it) was successfully validated by sending specific key and axis events to the mock real device and observing them on the virtual device created by `gamepad.py`.

*   **Overall Success & Refinements**:
    *   The implemented unit and integration tests validate the feasibility and effectiveness of the testing strategies outlined in this document.
    *   **Helper Patterns in Tests:** The use of `pytest` fixtures to manage external processes and resources (like `UInput` devices) proved to be a clean and robust pattern. If more complex test scenarios arise, creating dedicated helper functions or classes within the `tests` directory for these common tasks (e.g., a more configurable mock device factory, a generic subprocess manager) would be beneficial.
    *   **Logging in `gamepad.py`**: While not implemented as part of this initial test development, the process highlighted that more verbose logging within `gamepad.py` (using the `logging` module) would be extremely helpful for debugging both the script itself and the integration tests, especially when diagnosing timing issues or unexpected behavior in the subprocess.
    *   **Symlink Robustness:** The test for symlink creation in the `gamepad_process` fixture checks for existence. A more thorough check could involve `os.readlink()` to ensure it points to an actual `/dev/input/eventX` node, though this adds complexity as the exact event number is dynamic. For now, the functional event forwarding test implicitly validates the symlink's correctness.
