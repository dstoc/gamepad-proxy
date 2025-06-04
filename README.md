# Gamepad Docker Binding

This script creates a persistent virtual gamepad from a physical one, designed to be resilient to device reconnections. Its primary goal is to ensure that applications see a stable gamepad device even if the physical gamepad is unplugged and plugged back in. This makes it particularly useful for providing stable gamepad access to containerized applications, such as those running in Docker, without needing to restart containers on device changes.

## How it Works

The script continuously monitors for the specified gamepad device. When the device is detected, it creates a virtual gamepad device using `evdev` and `UInput`. It then forwards all events from the real gamepad to this virtual device. Symlinks are created in predictable locations (`/tmp/gamepad-event` and `/tmp/gamepad-js` by default) that point to the active event and joystick interfaces of this virtual gamepad. Applications within the Docker container can then be configured to use these symlinks, ensuring they always point to a valid device.

If the real gamepad disconnects, the script waits for it to reappear and then re-establishes the link, all without interrupting the virtual device that the containerized application is using (though no events will be forwarded while the real device is disconnected).

## Usage

## Installation

1.  Install the Rust toolchain via [rustup](https://rustup.rs/).
2.  Clone this repository:
    ```bash
    git clone <repository_url> # TODO: Replace <repository_url> with the actual URL
    cd <repository_directory> # TODO: Replace <repository_directory> with the actual directory name
    ```
3.  Build the project:
    ```bash
    cargo build --release
    ```
    The resulting binary will be located at `target/release/gamepad-proxy`.

## Running the Program

Use Cargo to run the binary:
```bash
cargo run -- [OPTIONS]
```
For example, to specify a custom device link:
```bash
cargo run -- --device-link /dev/input/by-id/your-device-id --event-path /tmp/custom-event
```

Available options for `gamepad-mapper`:
*   `--device-link`: Path to the real gamepad device link.
    *   Default: `/dev/input/by-id/usb-1038_SteelSeries_Stratus_Duo-event-joystick`
*   `--event-path`: Desired path for the event symlink.
    *   Default: `/tmp/gamepad-event`
*   `--js-path`: Desired path for the joystick symlink.
    *   Default: `/tmp/gamepad-js`
*   `--virtual-name`: Name for the virtual gamepad device.
    *   Default: `VirtualGamepad`

3.  **Inside the Docker container:**
    *   The `gamepad-proxy` binary creates symlinks on the host machine (e.g., `/tmp/gamepad-event` and `/tmp/gamepad-js` by default). To make the gamepad accessible inside your container, you should use the `--device` flag with `podman run` (or the equivalent for other container runtimes). This flag will map the actual gamepad device node (to which the symlink points) into your container.

        Example using default symlink paths:
        ```bash
        podman run --rm -it \
            --device=/tmp/gamepad-event \
            --device=/tmp/gamepad-js \
            your-container-image
        ```

        If you used custom paths for the symlinks when running `gamepad-proxy` (e.g., `/opt/gamepad/event` and `/opt/gamepad/js`), you would adjust the `--device` flags accordingly:
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

## Acknowledgements

The initial version of this script was developed with assistance from ChatGPT (model o3-mini-high). Subsequent refinements and feature development were contributed by Jules (Google).

## Future Development

*   Detailed testing strategy and implementation.

## Testing

A detailed testing strategy, including plans for unit and integration tests, is outlined in [TESTING.md](TESTING.md).

### Running Tests

The tests for this project are written in Rust using Cargo's built‑in test framework.

1. **Install the Rust toolchain** if you haven't already. The easiest way is via [rustup](https://rustup.rs/).

2. **Execute Tests:** Navigate to the project root and run:
    ```bash
    cargo test
    ```
