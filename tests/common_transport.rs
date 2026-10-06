//! Exercise patched common-library behavior through public APIs and real local IO.
use hbb_common::tokio;
use hbb_common::{
    bytes::BytesMut,
    fs,
    proxy::Proxy,
    tcp::{Encrypt, FramedStream},
    udp::FramedSocket,
};
use libsodium_rs::crypto_secretbox as secretbox;
use tokio::io::{AsyncReadExt, AsyncWriteExt};

#[tokio::test]
async fn tcp_timeout_then_frame_roundtrip() {
    let listener = hbb_common::tcp::new_listener("127.0.0.1:0", true)
        .await
        .unwrap();
    let address = listener.local_addr().unwrap();
    let mut client = FramedStream::new(address.to_string(), None, 1000)
        .await
        .unwrap();
    let (stream, peer) = listener.accept().await.unwrap();
    let mut server = FramedStream::from(stream, peer);
    assert!(client.next_timeout(10).await.is_none());
    server.send_raw(b"after-timeout".to_vec()).await.unwrap();
    assert_eq!(
        &client.next_timeout(1000).await.unwrap().unwrap()[..],
        b"after-timeout"
    );
}

#[tokio::test]
async fn udp_timeout_then_datagram_roundtrip() {
    let mut receiver = FramedSocket::new("127.0.0.1:0").await.unwrap();
    let mut sender = FramedSocket::new("127.0.0.1:0").await.unwrap();
    assert!(receiver.next_timeout(10).await.is_none());
    sender
        .send_raw(b"datagram", receiver.local_addr().unwrap())
        .await
        .unwrap();
    let (data, _) = receiver.next_timeout(1000).await.unwrap().unwrap();
    assert_eq!(&data[..], b"datagram");
}

#[test]
fn encrypted_frames_reject_tampering() {
    libsodium_rs::ensure_init().unwrap();
    let key = secretbox::Key::generate();
    let mut sender = Encrypt::new(key.clone());
    let mut receiver = Encrypt::new(key.clone());
    let mut data = BytesMut::from(&sender.enc(b"authenticated payload")[..]);
    receiver.dec(&mut data).unwrap();
    assert_eq!(&data[..], b"authenticated payload");
    let mut corrupted = sender.enc(b"second payload");
    corrupted[0] ^= 1;
    assert!(receiver.dec(&mut BytesMut::from(&corrupted[..])).is_err());
    assert!(Encrypt::new(secretbox::Key::generate())
        .dec(&mut BytesMut::from(
            &Encrypt::new(key).enc(b"wrong key")[..]
        ))
        .is_err());
}

#[test]
fn recursive_empty_directories_ignore_nonempty_and_hidden_entries() {
    let directory = tempfile::tempdir().unwrap();
    std::fs::create_dir_all(directory.path().join("nested/empty")).unwrap();
    std::fs::create_dir_all(directory.path().join(".hidden")).unwrap();
    std::fs::write(directory.path().join("nested/file"), b"content").unwrap();
    let visible = fs::get_empty_dirs_recursive(directory.path().to_str().unwrap(), false).unwrap();
    assert_eq!(visible.len(), 1);
    assert!(visible[0].path.ends_with("nested/empty"));
    let all = fs::get_empty_dirs_recursive(directory.path().to_str().unwrap(), true).unwrap();
    assert_eq!(all.len(), 2);
    assert!(
        fs::get_empty_dirs_recursive(directory.path().join("missing").to_str().unwrap(), true)
            .is_err()
    );
}

#[test]
fn filtered_fingerprint_is_stable_and_distinguishes_fields() {
    let platform = Some(vec!["platform".to_owned()]);
    let first = hbb_common::fingerprint::get_fingerprint(platform.clone(), None);
    assert!(!first.is_empty());
    assert_eq!(
        first,
        hbb_common::fingerprint::get_fingerprint(platform, None)
    );
    assert_ne!(
        first,
        hbb_common::fingerprint::get_fingerprint(Some(vec!["arch".to_owned()]), None)
    );
}

#[tokio::test]
async fn https_proxy_rejects_non_tls_peer() {
    let proxy = Proxy::new("https://localhost:443", 1000).unwrap();
    let (client, mut server) = tokio::io::duplex(4096);
    let peer = tokio::spawn(async move {
        let mut hello = [0; 4096];
        assert!(server.read(&mut hello).await.unwrap() > 0);
        server.write_all(b"HTTP/1.1 200 OK\r\n\r\n").await.unwrap();
    });
    let result = tokio::time::timeout(
        std::time::Duration::from_secs(2),
        proxy.https_connect_rustls(
            client,
            &hbb_common::TargetAddr::Domain("target.example".into(), 443),
            false,
        ),
    )
    .await
    .unwrap();
    assert!(result.is_err());
    peer.await.unwrap();
}

#[tokio::test]
async fn websocket_timeout_then_binary_frame_roundtrip() {
    use hbb_common::futures::{SinkExt, StreamExt};
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let peer = tokio::spawn(async move {
        let (stream, _) = listener.accept().await.unwrap();
        let mut websocket = tokio_tungstenite::accept_async(stream).await.unwrap();
        let message = websocket.next().await.unwrap().unwrap();
        assert_eq!(message.into_data().as_ref(), b"ws payload");
        websocket
            .send(tungstenite::Message::Binary(b"ws response".to_vec().into()))
            .await
            .unwrap();
    });
    let mut client =
        hbb_common::websocket::WsFramedStream::new(format!("ws://{address}"), None, None, 1000)
            .await
            .unwrap();
    assert!(client.next_timeout(10).await.is_none());
    client.send_raw(b"ws payload".to_vec()).await.unwrap();
    assert_eq!(
        &client.next_timeout(1000).await.unwrap().unwrap()[..],
        b"ws response"
    );
    peer.await.unwrap();
}

#[tokio::test]
async fn http_proxy_requires_successful_connect_response() {
    for (response, succeeds) in [
        (
            b"HTTP/1.1 200 Connection established\r\n\r\n".as_slice(),
            true,
        ),
        (b"HTTP/1.1 403 Forbidden\r\n\r\n".as_slice(), false),
    ] {
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let peer = tokio::spawn(async move {
            let (mut stream, _) = listener.accept().await.unwrap();
            let mut request = Vec::new();
            while !request.ends_with(b"\r\n\r\n") {
                let byte = stream.read_u8().await.unwrap();
                request.push(byte);
                assert!(request.len() < 4096);
            }
            assert!(request.starts_with(b"CONNECT target.example:443 HTTP/1.1\r\n"));
            stream.write_all(response).await.unwrap();
        });
        let proxy = Proxy::new(format!("http://{address}"), 1000).unwrap();
        assert!(proxy.is_http_or_https());
        assert_eq!(
            proxy.connect("target.example:443", None).await.is_ok(),
            succeeds
        );
        peer.await.unwrap();
    }
}

#[tokio::test]
async fn socks_proxy_preserves_explicit_address_and_rejects_bad_scheme() {
    let address = "127.0.0.1:1080".parse::<std::net::SocketAddr>().unwrap();
    let proxy = Proxy::new(format!("socks5://{address}"), 1000).unwrap();
    assert!(!proxy.is_http_or_https());
    assert_eq!(proxy.proxy_addrs().await.unwrap(), address);
    assert!(Proxy::new("ftp://127.0.0.1", 1000).is_err());
}

#[test]
fn transfer_paths_reject_traversal_and_symlink_escape() {
    let directory = tempfile::tempdir().unwrap();
    let base = directory.path();
    assert_eq!(fs::TransferJob::join(base, ""), base);
    assert_eq!(
        fs::join_validated_path(base, "report.txt").unwrap(),
        base.join("report.txt")
    );
    for name in ["../escape", "/absolute", "nested/../../escape"] {
        assert!(fs::join_validated_path(base, name).is_err());
    }
    #[cfg(unix)]
    {
        let outside = tempfile::tempdir().unwrap();
        std::os::unix::fs::symlink(outside.path(), base.join("link")).unwrap();
        assert!(fs::join_validated_path(base, "link/report.txt").is_err());
    }
    let report = base.join("report.txt");
    assert!(!fs::is_file_exists(report.to_str().unwrap()));
    std::fs::write(&report, b"report").unwrap();
    assert!(fs::is_file_exists(report.to_str().unwrap()));
}

#[test]
fn file_transfer_types_and_source_labels_preserve_wire_contracts() {
    assert_eq!(i32::from(fs::JobType::Generic), 0);
    assert_eq!(i32::from(fs::JobType::Printer), 1);
    assert_eq!(i32::from(fs::JobType::from(1)), 1);
    assert_eq!(i32::from(fs::JobType::from(99)), 0);
    assert_eq!(
        fs::DataSource::FilePath("report.txt".into()).to_string(),
        "File: report.txt"
    );
    assert_eq!(
        fs::DataSource::MemoryCursor(std::io::Cursor::new(vec![])).to_string(),
        "Bytes"
    );
}

#[test]
fn unset_connection_policy_allows_both_directions_and_tcp_listening() {
    assert!(!hbb_common::config::is_incoming_only());
    assert!(!hbb_common::config::is_outgoing_only());
    assert!(!hbb_common::config::is_disable_tcp_listen());
}

#[test]
fn encrypted_frames_preserve_pre_migration_wire_bytes() {
    // Independently generated with the libsodium 1.0.20 C API used by the
    // previous sodiumoxide build. This is a public synthetic test vector.
    let key = secretbox::Key::from_bytes(&(0u8..32).collect::<Vec<_>>()).unwrap();
    let expected = decode_hex(
        "ce5713a7b8587fdaf519ef1ac1ded876ae5eed419166d8a880190d2460072940a722481283db3f358ab2",
    );
    let mut sender = Encrypt::new(key.clone());
    assert_eq!(sender.enc(b"legacy frame compatibility"), expected);
    let mut receiver = Encrypt::new(key);
    let mut received = BytesMut::from(expected.as_slice());
    receiver.dec(&mut received).unwrap();
    assert_eq!(&received[..], b"legacy frame compatibility");
}

fn decode_hex(value: &str) -> Vec<u8> {
    assert_eq!(
        value.len() % 2,
        0,
        "Hex fixture must contain complete bytes"
    );
    value
        .as_bytes()
        .chunks_exact(2)
        .map(|pair| u8::from_str_radix(std::str::from_utf8(pair).unwrap(), 16).unwrap())
        .collect()
}

#[test]
fn ed25519_preserves_existing_key_files_and_rfc8032_signatures() {
    use libsodium_rs::crypto_sign as sign;
    // RFC 8032 section 7.1, TEST 1: public interoperability fixtures.
    let seed = decode_hex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60");
    let public = decode_hex("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a");
    let signature = decode_hex(concat!(
        "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155",
        "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"
    ));
    let mut stored = seed;
    stored.extend(&public);
    let secret = sign::SecretKey::from_bytes(&stored).unwrap();
    let public = sign::PublicKey::from_bytes(&public).unwrap();
    assert_eq!(sign::sign(b"", &secret).unwrap(), signature);
    assert_eq!(sign::verify(&signature, &public), Some(Vec::new()));
    let mut corrupted = signature;
    corrupted[0] ^= 1;
    assert!(sign::verify(&corrupted, &public).is_none());
}

#[test]
fn linked_libsodium_includes_the_native_security_fixes() {
    let version = libsodium_rs::version::version_string();
    let numbers: Vec<u32> = version
        .split('-')
        .next()
        .unwrap()
        .split('.')
        .map(|part| part.parse().unwrap())
        .collect();
    assert_eq!(numbers.len(), 3);
    assert!(
        numbers.as_slice() >= [1, 0, 21].as_slice(),
        "Native libsodium is older than the patched minimum"
    );
}
