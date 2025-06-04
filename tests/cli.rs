use assert_cmd::Command;
use predicates::prelude::*;

#[test]
fn help_shows_options() {
    let mut cmd = Command::cargo_bin("gamepad-proxy").unwrap();
    cmd.arg("--help").assert()
        .success()
        .stdout(predicate::str::contains("--device-link"));
}

#[test]
fn version_shows_version() {
    let mut cmd = Command::cargo_bin("gamepad-proxy").unwrap();
    cmd.arg("--version").assert()
        .success()
        .stdout(predicate::str::contains(env!("CARGO_PKG_VERSION")));
}
