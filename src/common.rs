use clap::{Arg, Command};
use hbb_common::{
    allow_err,
    anyhow::{Context, Result},
    get_version_number, log, tokio, ResultType,
};
use ini::Ini;
use libsodium_rs::crypto_sign as sign;
use std::{
    io::prelude::*,
    io::Read,
    net::SocketAddr,
    time::{Instant, SystemTime},
};

#[allow(dead_code)]
pub(crate) fn get_expired_time() -> Instant {
    let now = Instant::now();
    now.checked_sub(std::time::Duration::from_secs(3600))
        .unwrap_or(now)
}

#[allow(dead_code)]
pub(crate) fn test_if_valid_server(host: &str, name: &str) -> ResultType<SocketAddr> {
    use std::net::ToSocketAddrs;
    let res = if host.contains(':') {
        host.to_socket_addrs()?.next().context("")
    } else {
        format!("{}:{}", host, 0)
            .to_socket_addrs()?
            .next()
            .context("")
    };
    if res.is_err() {
        log::error!("Invalid {} {}: {:?}", name, host, res);
    }
    res
}

#[allow(dead_code)]
pub(crate) fn get_servers(s: &str, tag: &str) -> Vec<String> {
    let servers: Vec<String> = s
        .split(',')
        .filter(|x| !x.is_empty() && test_if_valid_server(x, tag).is_ok())
        .map(|x| x.to_owned())
        .collect();
    log::info!("{}={:?}", tag, servers);
    servers
}

#[allow(dead_code)]
#[inline]
fn arg_name(name: &str) -> String {
    name.to_uppercase().replace('_', "-")
}

#[allow(dead_code)]
pub fn init_args(name: &'static str, about: &'static str) {
    let matches = server_command(name)
        .version(crate::version::VERSION)
        .author("Purslane Ltd. <info@rustdesk.com>")
        .about(about)
        .get_matches();
    if let Ok(v) = Ini::load_from_file(".env") {
        if let Some(section) = v.section(None::<String>) {
            section
                .iter()
                .for_each(|(k, v)| std::env::set_var(arg_name(k), v));
        }
    }
    if let Some(config) = matches.get_one::<String>("config") {
        if let Ok(v) = Ini::load_from_file(config) {
            if let Some(section) = v.section(None::<String>) {
                section
                    .iter()
                    .for_each(|(k, v)| std::env::set_var(arg_name(k), v));
            }
        }
    }
    for id in matches.ids() {
        if let Some(value) = matches.get_one::<String>(id.as_str()) {
            std::env::set_var(arg_name(id.as_str()), value);
        }
    }
}

#[allow(dead_code)]
#[inline]
pub fn get_arg(name: &str) -> String {
    get_arg_or(name, "".to_owned())
}

#[allow(dead_code)]
#[inline]
pub fn get_arg_or(name: &str, default: String) -> String {
    std::env::var(arg_name(name)).unwrap_or(default)
}

#[allow(dead_code)]
#[inline]
pub fn now() -> u64 {
    SystemTime::now()
        .duration_since(SystemTime::UNIX_EPOCH)
        .map(|x| x.as_secs())
        .unwrap_or_default()
}

pub fn gen_sk(wait: u64) -> (String, Option<sign::SecretKey>) {
    let sk_file = "id_ed25519";
    if wait > 0 && !std::path::Path::new(sk_file).exists() {
        std::thread::sleep(std::time::Duration::from_millis(wait));
    }
    if let Ok(mut file) = std::fs::File::open(sk_file) {
        let mut contents = String::new();
        if file.read_to_string(&mut contents).is_ok() {
            let contents = contents.trim();
            let sk = base64::decode(contents).unwrap_or_default();
            if sk.len() == sign::SECRETKEYBYTES {
                let mut tmp = [0u8; sign::SECRETKEYBYTES];
                tmp[..].copy_from_slice(&sk);
                let pk = base64::encode(&tmp[sign::SECRETKEYBYTES / 2..]);
                log::info!("Private key comes from {}", sk_file);
                return (pk, Some(sign::SecretKey::from_bytes_exact(tmp)));
            } else {
                // don't use log here, since it is async
                println!("Fatal error: malformed private key in {sk_file}.");
                std::process::exit(1);
            }
        }
    } else {
        let gen_func = || {
            let (tmp, sk) = hbb_common::generate_signing_keypair();
            (base64::encode(tmp), sk)
        };
        let (mut pk, mut sk) = gen_func();
        for _ in 0..300 {
            if !pk.contains('/') && !pk.contains(':') {
                break;
            }
            (pk, sk) = gen_func();
        }
        let pub_file = format!("{sk_file}.pub");
        if let Ok(mut f) = std::fs::File::create(&pub_file) {
            f.write_all(pk.as_bytes()).ok();
            if let Ok(mut f) = std::fs::File::create(sk_file) {
                let s = base64::encode(&sk);
                if f.write_all(s.as_bytes()).is_ok() {
                    log::info!("Private/public key written to {}/{}", sk_file, pub_file);
                    log::debug!("Public key: {}", pk);
                    return (pk, Some(sk));
                }
            }
        }
    }
    ("".to_owned(), None)
}

#[cfg(unix)]
pub async fn listen_signal() -> Result<()> {
    use hbb_common::tokio;
    use hbb_common::tokio::signal::unix::{signal, SignalKind};

    tokio::spawn(async {
        let mut s = signal(SignalKind::terminate())?;
        let terminate = s.recv();
        let mut s = signal(SignalKind::interrupt())?;
        let interrupt = s.recv();
        let mut s = signal(SignalKind::quit())?;
        let quit = s.recv();

        tokio::select! {
            _ = terminate => {
                log::info!("signal terminate");
            }
            _ = interrupt => {
                log::info!("signal interrupt");
            }
            _ = quit => {
                log::info!("signal quit");
            }
        }
        Ok(())
    })
    .await?
}

#[cfg(not(unix))]
pub async fn listen_signal() -> Result<()> {
    let () = std::future::pending().await;
    unreachable!();
}

pub fn check_software_update() {
    const ONE_DAY_IN_SECONDS: u64 = 60 * 60 * 24;
    std::thread::spawn(move || loop {
        std::thread::spawn(move || allow_err!(check_software_update_()));
        std::thread::sleep(std::time::Duration::from_secs(ONE_DAY_IN_SECONDS));
    });
}

#[tokio::main(flavor = "current_thread")]
async fn check_software_update_() -> hbb_common::ResultType<()> {
    let (request, url) =
        hbb_common::version_check_request(hbb_common::VER_TYPE_RUSTDESK_SERVER.to_string());
    let latest_release_response = reqwest::Client::builder()
        .build()?
        .post(url)
        .json(&request)
        .send()
        .await?;

    let bytes = latest_release_response.bytes().await?;
    let resp: hbb_common::VersionCheckResponse = serde_json::from_slice(&bytes)?;
    let response_url = resp.url;
    let latest_release_version = response_url.rsplit('/').next().unwrap_or_default();
    if get_version_number(latest_release_version) > get_version_number(crate::version::VERSION) {
        log::info!("new version is available: {}", latest_release_version);
    }
    Ok(())
}

/// Shared explicit CLI contract; environment and INI precedence stays in callers.
pub fn server_command(name: &'static str) -> Command {
    let mut command = Command::new(name);
    let options = [
        ("port", Some('p'), "Listening port"),
        ("key", Some('k'), "Required client key"),
    ];
    for (id, short, help) in options {
        let mut arg = Arg::new(id).long(id).num_args(1).help(help);
        if let Some(short) = short {
            arg = arg.short(short);
        }
        command = command.arg(arg);
    }
    if name == "hbbs" {
        for (id, short, help) in [
            ("config", Some('c'), "Custom INI configuration file"),
            (
                "serial",
                Some('s'),
                "Deprecated configuration serial number",
            ),
            (
                "rendezvous-servers",
                Some('R'),
                "Deprecated rendezvous servers",
            ),
            (
                "software-url",
                Some('u'),
                "Deprecated software download URL",
            ),
            ("relay-servers", Some('r'), "Default relay servers"),
            ("rmem", Some('M'), "UDP receive buffer size"),
            ("mask", None, "Deprecated LAN mask"),
        ] {
            let mut arg = Arg::new(id).long(id).num_args(1).help(help);
            if let Some(short) = short {
                arg = arg.short(short);
            }
            command = command.arg(arg);
        }
    }
    command
}

#[cfg(test)]
mod cli_contract_tests {
    #[test]
    fn rendezvous_flags_keep_names_values_and_negative_key() {
        let matches = super::server_command("hbbs")
            .try_get_matches_from([
                "hbbs",
                "-c",
                "server.ini",
                "-p",
                "21116",
                "-s",
                "0",
                "-R",
                "host",
                "-u",
                "https://example.invalid",
                "-r",
                "relay",
                "-M",
                "1024",
                "--mask",
                "10.0.0.0/8",
                "-k",
                "-",
            ])
            .unwrap();
        assert_eq!(
            matches.get_one::<String>("key").map(String::as_str),
            Some("-")
        );
        assert_eq!(
            matches.get_one::<String>("config").map(String::as_str),
            Some("server.ini")
        );
        assert!(super::server_command("hbbr")
            .try_get_matches_from(["hbbr", "--relay-servers", "host"])
            .is_err());
        assert!(super::server_command("hbbs")
            .try_get_matches_from(["hbbs", "--port"])
            .is_err());
    }
}
