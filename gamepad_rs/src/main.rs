use clap::Parser;

/// A simple program to create a virtual gamepad
#[derive(Parser, Debug)]
#[clap(author, version, about, long_about = None)]
struct Args {
    /// Path to the physical gamepad device link
    #[clap(short = 'd', long, default_value = "/dev/input/by-id/usb-1038_SteelSeries_Stratus_Duo-event-joystick")]
    device_link: String,

    /// Path to the event file for the virtual gamepad
    #[clap(short = 'e', long, default_value = "/tmp/gamepad-event")]
    event_path: String,

    /// Path to the js file for the virtual gamepad
    #[clap(short = 'j', long, default_value = "/tmp/gamepad-js")]
    js_path: String,

    /// Name for the virtual gamepad
    #[clap(short = 'n', long, default_value = "VirtualGamepad")]
    virtual_name: String,
}

fn main() {
    let args = Args::parse();
    println!("{:?}", args);
}
