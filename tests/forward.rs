use assert_cmd::prelude::*;
use std::process::Command;
use evdev::{uinput::VirtualDevice, AttributeSet, InputEvent, KeyCode, EventType, Device};
use std::{thread, time::Duration};
use tempfile::TempDir;

#[test]
fn forwards_key_event() -> Result<(), Box<dyn std::error::Error>> {
    if !std::path::Path::new("/dev/uinput").exists() {
        eprintln!("Skipping test; /dev/uinput missing");
        return Ok(());
    }
    // Create a virtual "real" device generating KEY_A events
    let mut keys = AttributeSet::<KeyCode>::new();
    keys.insert(KeyCode::KEY_A);
    let mut real_dev = VirtualDevice::builder()?
        .name(b"TestSource")
        .with_keys(&keys)?
        .build()?;
    let event_src = real_dev.enumerate_dev_nodes_blocking()?.next().unwrap()?;

    // Temporary directory for symlinks
    let dir = TempDir::new()?;
    let event_link = dir.path().join("event");
    let js_link = dir.path().join("js");

    // Launch proxy
    let mut child = Command::cargo_bin("gamepad-proxy")?
        .args([
            "--device-link", event_src.to_str().unwrap(),
            "--event-path", event_link.to_str().unwrap(),
            "--js-path", js_link.to_str().unwrap(),
            "--virtual-name", "ForwardedDevice",
        ])
        .spawn()?;

    for _ in 0..50 {
        if event_link.exists() { break; }
        thread::sleep(Duration::from_millis(50));
    }
    if !event_link.exists() {
        child.kill().ok();
        child.wait().ok();
        return Err("event symlink not created".into());
    }

    let mut out_dev = Device::open(&event_link)?;
    out_dev.set_nonblocking(true)?;

    real_dev.emit(&[InputEvent::new(EventType::KEY.0, KeyCode::KEY_A.0, 1)])?;
    real_dev.emit(&[InputEvent::new(EventType::KEY.0, KeyCode::KEY_A.0, 0)])?;

    let mut received = false;
    for _ in 0..20 {
        if let Ok(iter) = out_dev.fetch_events() {
            for ev in iter {
                if ev.event_type() == EventType::KEY && ev.code() == KeyCode::KEY_A.0 {
                    received = true;
                    break;
                }
            }
        }
        if received { break; }
        thread::sleep(Duration::from_millis(50));
    }

    child.kill().ok();
    child.wait().ok();
    if !received {
        return Err("Forwarded event not received".into());
    }
    Ok(())
}
