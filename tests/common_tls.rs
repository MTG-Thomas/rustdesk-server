//! Exercise the production HTTPS proxy connectors against an untrusted server.
use hbb_common::{proxy::Proxy, tokio, TargetAddr};
use std::sync::Arc;
use tokio_rustls::{rustls, TlsAcceptor};

async fn untrusted_proxy() -> (Proxy, tokio::task::JoinHandle<()>) {
    let identity = rcgen::generate_simple_self_signed(vec!["127.0.0.1".to_owned()]).unwrap();
    let key = rustls::pki_types::PrivatePkcs8KeyDer::from(identity.signing_key.serialize_der());
    let config = rustls::ServerConfig::builder()
        .with_no_client_auth()
        .with_single_cert(vec![identity.cert.der().clone()], key.into())
        .unwrap();
    let acceptor = TlsAcceptor::from(Arc::new(config));
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let port = listener.local_addr().unwrap().port();
    let proxy = Proxy::new(format!("https://127.0.0.1:{port}"), 1000).unwrap();
    let server = tokio::spawn(async move {
        let (stream, _) = listener.accept().await.unwrap();
        // A successful CONNECT request must never reach an untrusted proxy.
        if let Ok(mut tls) = acceptor.accept(stream).await {
            use tokio::io::AsyncReadExt;
            let mut byte = [0];
            assert!(!matches!(tls.read(&mut byte).await, Ok(1)));
        }
    });
    (proxy, server)
}

#[tokio::test]
async fn rustls_proxy_rejects_untrusted_certificate() {
    let (proxy, server) = untrusted_proxy().await;
    // connect() includes the production Rustls -> native TLS retry path.
    assert!(proxy.connect("example.invalid:443", None).await.is_err());
    tokio::time::timeout(std::time::Duration::from_secs(2), server)
        .await
        .unwrap()
        .unwrap();
}

#[tokio::test]
async fn explicit_bypass_is_rejected_before_using_the_stream() {
    let proxy = Proxy::new("https://localhost:443", 1000).unwrap();
    let target = TargetAddr::Domain("example.invalid".into(), 443);
    let (stream, _peer) = tokio::io::duplex(1024);
    assert!(proxy
        .https_connect_nativetls(stream, &target, true)
        .await
        .is_err());
    let (stream, _peer) = tokio::io::duplex(1024);
    assert!(proxy
        .https_connect_rustls(stream, &target, true)
        .await
        .is_err());
}

#[tokio::test]
async fn native_tls_proxy_rejects_untrusted_certificate() {
    let (proxy, server) = untrusted_proxy().await;
    let stream = tokio::net::TcpStream::connect(proxy.proxy_addrs().await.unwrap())
        .await
        .unwrap();
    let target = TargetAddr::Domain("example.invalid".into(), 443);
    assert!(proxy
        .https_connect_nativetls(stream, &target, false)
        .await
        .is_err());
    tokio::time::timeout(std::time::Duration::from_secs(2), server)
        .await
        .unwrap()
        .unwrap();
}

#[tokio::test]
async fn secure_websocket_rejects_untrusted_certificate() {
    let (proxy, server) = untrusted_proxy().await;
    let address = proxy.proxy_addrs().await.unwrap();
    assert!(hbb_common::websocket::WsFramedStream::new(
        format!("wss://{address}"),
        None,
        None,
        1000,
    )
    .await
    .is_err());
    tokio::time::timeout(std::time::Duration::from_secs(2), server)
        .await
        .unwrap()
        .unwrap();
}
