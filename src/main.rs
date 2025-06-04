use clap::Parser;
use evdev::{Device, InputEvent, UinputAbsSetup, uinput::VirtualDevice, AbsInfo};
use std::{path::{PathBuf, Path}, thread, time::Duration, fs};

#[derive(Parser, Debug)]
#[command(author, version, about)]
struct Args {
    #[arg(long, default_value = "/dev/input/by-id/usb-1038_SteelSeries_Stratus_Duo-event-joystick")]
    device_link: PathBuf,
    #[arg(long, default_value = "/tmp/gamepad-event")]
    event_path: PathBuf,
    #[arg(long, default_value = "/tmp/gamepad-js")]
    js_path: PathBuf,
    #[arg(long, default_value = "VirtualGamepad")]
    virtual_name: String,
}

fn wait_for_device(path: &Path) -> Device {
    loop {
        match Device::open(path) {
            Ok(dev) => {
                println!("\u{2705} Opened real device: {}", dev.name().unwrap_or("unknown"));
                return dev;
            }
            Err(e) => {
                eprintln!("Could not open {path:?}: {e}");
                thread::sleep(Duration::from_secs(1));
            }
        }
    }
}

fn build_virtual(real: &Device, name: &str) -> std::io::Result<VirtualDevice> {
    let id = real.input_id();
    let mut builder = VirtualDevice::builder()?;
    builder = builder.name(name).input_id(id);
    if let Some(keys) = real.supported_keys() {
        builder = builder.with_keys(keys)?;
    }
    if let Ok(absinfo_iter) = real.get_absinfo() {
        for (code, info) in absinfo_iter {
            let setup = UinputAbsSetup::new(
                code,
                AbsInfo::new(
                    info.value(),
                    info.minimum(),
                    info.maximum(),
                    info.fuzz(),
                    info.flat(),
                    info.resolution(),
                ),
            );
            builder = builder.with_absolute_axis(&setup)?;
        }
    }
    builder.build()
}

fn create_symlinks(name: &str, event_path: &Path, js_path: &Path) -> std::io::Result<bool> {
    let sys_input = Path::new("/sys/class/input");
    for entry in fs::read_dir(sys_input)? {
        let entry = entry?;
        let file_name = entry.file_name();
        if !file_name.to_string_lossy().starts_with("input") { continue; }
        let name_file = entry.path().join("name");
        if let Ok(n) = fs::read_to_string(&name_file) {
            if n.trim() == name {
                for child in fs::read_dir(entry.path())? {
                    let child = child?;
                    let fname = child.file_name();
                    let src = child.path();
                    if fname.to_string_lossy().starts_with("event") {
                        if src.exists() {
                            if let Some(parent) = event_path.parent() { fs::create_dir_all(parent)?; }
                            let _ = fs::remove_file(event_path);
                            std::os::unix::fs::symlink(&src, event_path)?;
                            println!("\u{1f517} {} -> {}", event_path.display(), src.display());
                        }
                    } else if fname.to_string_lossy().starts_with("js") {
                        if src.exists() {
                            if let Some(parent) = js_path.parent() { fs::create_dir_all(parent)?; }
                            let _ = fs::remove_file(js_path);
                            std::os::unix::fs::symlink(&src, js_path)?;
                            println!("\u{1f517} {} -> {}", js_path.display(), src.display());
                        }
                    }
                }
                return Ok(true);
            }
        }
    }
    Ok(false)
}

fn forward_loop(args: &Args) -> std::io::Result<()> {
    loop {
        let mut real = wait_for_device(&args.device_link);
        let mut virt = build_virtual(&real, &args.virtual_name)?;
        let _ = create_symlinks(&args.virtual_name, &args.event_path, &args.js_path);
        real.grab()?;
        println!("\u{25b6}\u{fe0f} Forwarding events...");
        loop {
            match real.fetch_events() {
                Ok(iter) => {
                    let events: Vec<InputEvent> = iter.collect();
                    if events.is_empty() {
                        thread::sleep(Duration::from_millis(10));
                        continue;
                    }
                    virt.emit(&events)?;
                }
                Err(e) => {
                    eprintln!("Disconnected: {e}, waiting...");
                    break;
                }
            }
        }
        thread::sleep(Duration::from_secs(1));
    }
}

fn main() -> std::io::Result<()> {
    let args = Args::parse();
    forward_loop(&args)
}

