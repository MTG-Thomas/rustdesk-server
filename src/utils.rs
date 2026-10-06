use dns_lookup::{lookup_addr, lookup_host};
use hbb_common::{bail, ResultType};
use libsodium_rs::crypto_sign as sign;
use std::{
    env,
    net::{IpAddr, TcpStream},
    process, str,
};

fn print_help() {
    println!(
        "Usage:
    rustdesk-utils [command]\n
Available Commands:
    genkeypair [private-key-file]                Generate a keypair (default file: id_ed25519)
    validatekeypair [public key] [secret key]    Validate an existing keypair
    doctor [rustdesk-server]                     Check for server connection problems"
    );
    process::exit(0x0001);
}

fn error_then_help(msg: &str) {
    println!("ERROR: {msg}\n");
    print_help();
}

fn gen_keypair(path: &std::path::Path) -> ResultType<()> {
    use std::io::Write;
    let (pk, sk) = hbb_common::generate_signing_keypair();
    let mut options = std::fs::OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut file = options.open(path)?;
    file.write_all(base64::encode(sk).as_bytes())?;
    file.sync_all()?;
    println!("Public Key:  {}", base64::encode(pk));
    println!("Private key saved to the requested file.");
    Ok(())
}

fn validate_keypair(pk: &str, sk: &str) -> ResultType<()> {
    let secret_bytes = base64::decode(sk)?;
    let secret_key = sign::SecretKey::from_bytes(&secret_bytes)?;
    let public_bytes = base64::decode(pk)?;
    let public_key = sign::PublicKey::from_bytes(&public_bytes)?;
    let message = b"This is meh.";
    let signed = sign::sign(message, &secret_key)?;
    if sign::verify(&signed, &public_key).as_deref() != Some(message.as_slice()) {
        bail!("Key pair is INVALID");
    }

    Ok(())
}

fn doctor_tcp(address: std::net::IpAddr, port: &str, desc: &str) {
    let start = std::time::Instant::now();
    let conn = format!("{address}:{port}");
    if let Ok(_stream) = TcpStream::connect(conn.as_str()) {
        let elapsed = std::time::Instant::now().duration_since(start);
        println!(
            "TCP Port {} ({}): OK in {} ms",
            port,
            desc,
            elapsed.as_millis()
        );
    } else {
        println!("TCP Port {port} ({desc}): ERROR");
    }
}

fn doctor_ip(server_ip_address: std::net::IpAddr, server_address: Option<&str>) {
    println!("\nChecking IP address: {server_ip_address}");
    println!("Is IPV4: {}", server_ip_address.is_ipv4());
    println!("Is IPV6: {}", server_ip_address.is_ipv6());

    // reverse dns lookup
    // TODO: (check) doesn't seem to do reverse lookup on OSX...
    let reverse = lookup_addr(&server_ip_address).unwrap();
    if let Some(server_address) = server_address {
        if reverse == server_address {
            println!("Reverse DNS lookup: '{reverse}' MATCHES server address");
        } else {
            println!(
                "Reverse DNS lookup: '{reverse}' DOESN'T MATCH server address '{server_address}'"
            );
        }
    }

    // TODO: ICMP ping?

    // port check TCP (UDP is hard to check)
    doctor_tcp(server_ip_address, "21114", "API");
    doctor_tcp(server_ip_address, "21115", "hbbs extra port for nat test");
    doctor_tcp(server_ip_address, "21116", "hbbs");
    doctor_tcp(server_ip_address, "21117", "hbbr tcp");
    doctor_tcp(server_ip_address, "21118", "hbbs websocket");
    doctor_tcp(server_ip_address, "21119", "hbbr websocket");

    // TODO: key check
}

fn doctor(server_address_unclean: &str) {
    let server_address3 = server_address_unclean.trim();
    let server_address2 = server_address3.to_lowercase();
    let server_address = server_address2.as_str();
    println!("Checking server:  {server_address}\n");
    if let Ok(server_ipaddr) = server_address.parse::<IpAddr>() {
        // user requested an ip address
        doctor_ip(server_ipaddr, None);
    } else {
        // the passed string is not an ip address
        let ips: Vec<std::net::IpAddr> = lookup_host(server_address).unwrap();
        println!("Found {} IP addresses: ", ips.len());

        ips.iter().for_each(|ip| println!(" - {ip}"));

        ips.iter()
            .for_each(|ip| doctor_ip(*ip, Some(server_address)));
    }
}

fn main() {
    let args: Vec<_> = env::args().collect();
    if args.len() <= 1 {
        print_help();
    }

    let command = args[1].to_lowercase();
    match command.as_str() {
        "genkeypair" => {
            let path = args.get(2).map(String::as_str).unwrap_or("id_ed25519");
            if gen_keypair(std::path::Path::new(path)).is_err() {
                eprintln!(
                    "Unable to create private key file; existing files are never overwritten."
                );
                process::exit(1);
            }
        }
        "validatekeypair" => {
            if args.len() <= 3 {
                error_then_help("You must supply both the public and the secret key");
            }
            let res = validate_keypair(args[2].as_str(), args[3].as_str());
            if let Err(e) = res {
                println!("{e}");
                process::exit(0x0001);
            }
            println!("Key pair is VALID");
        }
        "doctor" => {
            if args.len() <= 2 {
                error_then_help("You must supply the rustdesk-server address");
            }
            doctor(args[2].as_str());
        }
        _ => print_help(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn generated_private_key_is_valid_and_existing_file_is_preserved() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("key");
        gen_keypair(&path).unwrap();
        let encoded = std::fs::read_to_string(&path).unwrap();
        let key = base64::decode(&encoded).unwrap();
        let public = base64::encode(&key[32..]);
        validate_keypair(&public, &encoded).unwrap();
        assert!(gen_keypair(&path).is_err());
        assert_eq!(std::fs::read_to_string(&path).unwrap(), encoded);
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            assert_eq!(
                std::fs::metadata(&path).unwrap().permissions().mode() & 0o777,
                0o600
            );
        }
    }

    #[cfg(unix)]
    #[test]
    fn private_key_generation_rejects_symlinks() {
        let directory = tempfile::tempdir().unwrap();
        let target = directory.path().join("target");
        std::fs::write(&target, b"untouched").unwrap();
        let link = directory.path().join("link");
        std::os::unix::fs::symlink(&target, &link).unwrap();
        assert!(gen_keypair(&link).is_err());
        assert_eq!(std::fs::read(target).unwrap(), b"untouched");
    }
}
