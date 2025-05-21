# Gamepad Docker Binding

This script facilitates binding a gamepad device into a Docker container, enabling its use within containerized applications. A key feature of this script is its ability to handle device reconnections seamlessly, meaning the Docker container does not need to be restarted if the gamepad is unplugged and plugged back in.

## How it Works

The script continuously monitors for the specified gamepad device. When the device is detected, it creates a virtual gamepad device using `evdev` and `UInput`. It then forwards all events from the real gamepad to this virtual device. Symlinks are created in predictable locations (`/tmp/gamepad-event` and `/tmp/gamepad-js` by default) that point to the active event and joystick interfaces of this virtual gamepad. Applications within the Docker container can then be configured to use these symlinks, ensuring they always point to a valid device.

If the real gamepad disconnects, the script waits for it to reappear and then re-establishes the link, all without interrupting the virtual device that the containerized application is using (though no events will be forwarded while the real device is disconnected).

## Usage

1.  **Installation:**
    1.  Install `uv` if you haven't already (see [uv's installation guide](https://github.com/astral-sh/uv#installation)).
    2.  Clone this repository.
    3.  Navigate to the cloned directory.
    4.  The following commands set up the environment:
        ```bash
        uv venv # Creates a virtual environment using .python-version if present
        source .venv/bin/activate # Or .venv\Scripts\activate on Windows
        uv pip install .[dev] # Installs runtime and development dependencies
        ```
    This project includes a `.python-version` file specifying a compatible Python version (e.g., 3.7 or higher). If you have a Python version manager like `pyenv` installed, it might automatically pick up this version. `uv` will also use this version to create the virtual environment if the specified Python interpreter is available. Otherwise, `uv` will use a compatible Python version found on your system.

2.  **Running the script:**

    ### Method 1: Using `python3` (with activated environment)

    Ensure your virtual environment is activated (`source .venv/bin/activate`):
    ```bash
    python3 gamepad.py [OPTIONS]
    ```
    Available options:
    *   `--device-link`: Path to the real gamepad device link.
        *   Default: `/dev/input/by-id/usb-1038_SteelSeries_Stratus_Duo-event-joystick`
    *   `--event-path`: Desired path for the event symlink.
        *   Default: `/tmp/gamepad-event`
    *   `--js-path`: Desired path for the joystick symlink.
        *   Default: `/tmp/gamepad-js`
    *   `--virtual-name`: Name for the virtual gamepad device.
        *   Default: `VirtualGamepad`

    For example:
    ```bash
    python3 gamepad.py --device-link /dev/input/by-id/your-device-id
    ```

    ### Method 2: Using `uv run`

    Alternatively, after installing dependencies (with `uv pip install .[dev]`), you can use `uv run` to execute the script. This command runs scripts defined in `pyproject.toml` within the project's managed environment.
    The script is registered as `gamepad-mapper`.
    ```bash
    uv run gamepad-mapper -- [OPTIONS]
    ```
    For example, to specify a custom device link:
    ```bash
    uv run gamepad-mapper -- --device-link /dev/input/by-id/your-device-id
    ```
    Note the `--` separator between `uv run gamepad-mapper` and the script's own options. This tells `uv` that subsequent arguments are for the script, not for `uv` itself.

3.  **Inside the Docker container:**
    *   The `gamepad.py` script creates symlinks on the host machine (e.g., `/tmp/gamepad-event` and `/tmp/gamepad-js` by default). To make the gamepad accessible inside your container, you should use the `--device` flag with `podman run` (or the equivalent for other container runtimes). This flag will map the actual gamepad device node (to which the symlink points) into your container.

        Example using default symlink paths:
        ```bash
        podman run --rm -it \
            --device=/tmp/gamepad-event \
            --device=/tmp/gamepad-js \
            your-container-image
        ```

        If you used custom paths for the symlinks when running `gamepad.py` (e.g., `/opt/gamepad/event` and `/opt/gamepad/js`), you would adjust the `--device` flags accordingly:
        ```bash
        podman run --rm -it \
            --device=/opt/gamepad/event \
            --device=/opt/gamepad/js \
            your-container-image
        ```
        Inside the container, your application can then access the gamepad directly at `/tmp/gamepad-event` (or `/opt/gamepad/event`, etc.), as the `--device` flag typically makes the device available at the same path within the container as specified on the host.
    *   Configure your application to use the gamepad device via these paths within the container (e.g., `/tmp/gamepad-event`).

## Key Features

*   **Resilient to Reconnections:** No need to restart your Docker container if the gamepad is reconnected.
*   **Stable Device Path:** Provides stable symlinks to the gamepad events, even if the underlying `/dev/input/event*` number changes.
*   **Customizable:** Device paths and names can be configured via command-line arguments.

## Future Development

*   Detailed testing strategy and implementation.

## Testing

A detailed testing strategy, including plans for unit and integration tests, is outlined in [TESTING.md](TESTING.md).

### Running Tests

The tests for this project are written using `pytest`.

1.  **Install Dependencies:** First, ensure you have installed the development dependencies. If you followed the installation steps above, `uv pip install .[dev]` will have installed `pytest`.

2.  **Execute Tests:** To run the tests, navigate to the root of the project directory and execute:
    ```bash
    pytest tests/
    ```

3.  **Running Tests Requiring `UInput` Permissions:** Some integration tests interact with `evdev.UInput` to create virtual devices. Access to `/dev/uinput` (which `UInput` uses) requires appropriate permissions.
    *   On many systems, this is managed by `udev` rules, which might grant access to users in a specific group (e.g., `input` or `uinput`). Ensure your user is part of such a group (e.g., by running `sudo usermod -aG input $USER` and then logging out and back in).
    *   If tests fail due to permission errors related to `/dev/uinput`, please check your system's udev rules (often in `/etc/udev/rules.d/` or `/lib/udev/rules.d/`) and your user's group memberships. You may need to create or modify a udev rule to grant your user write access to `/dev/uinput`. For example, a rule like `KERNEL=="uinput", MODE="0660", GROUP="input", OPTIONS+="static_node=uinput"` could be used.
    *   The tests that require these permissions are designed to skip themselves automatically if they detect insufficient privileges, rather than failing outright.
    *   While running tests with `sudo pytest tests/` might bypass these permission checks, it's recommended to configure user permissions correctly. This approach is more secure and ensures that both the application and its tests can run under normal user privileges where possible.
