//! Verify the key-generation CLI never emits its private key.
#[test]
fn private_key_is_saved_without_reaching_stdout_or_stderr() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("private-key");
    let output = std::process::Command::new(env!("CARGO_BIN_EXE_rustdesk-utils"))
        .arg("genkeypair")
        .arg(&path)
        .output()
        .unwrap();
    assert!(output.status.success());
    let key = std::fs::read_to_string(&path).unwrap();
    assert!(!key.is_empty());
    let stdout = String::from_utf8(output.stdout).unwrap();
    let stderr = String::from_utf8(output.stderr).unwrap();
    assert!(stdout.contains("Public Key:"));
    assert!(!stdout.contains("Secret Key:"));
    assert!(!stdout.contains(key.as_str()));
    assert!(!stderr.contains(key.as_str()));
    let repeat = std::process::Command::new(env!("CARGO_BIN_EXE_rustdesk-utils"))
        .arg("genkeypair")
        .arg(&path)
        .output()
        .unwrap();
    assert!(!repeat.status.success());
    assert_eq!(std::fs::read_to_string(path).unwrap(), key);
}
