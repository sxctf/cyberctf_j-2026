mod auth;
mod bank;
mod commands;
mod plugin;

use bank::Bank;
use commands::{Handler, Reply, MENU};
use std::sync::{Arc, Mutex};
use std::time::Duration;
use tokio::io::{AsyncBufReadExt, AsyncReadExt, AsyncWriteExt, BufReader};
use tokio::net::{TcpListener, TcpStream};
use tokio::sync::Semaphore;
use tokio::time::timeout;

const DEFAULT_PORT: u16 = 7777;
const MAX_CONNECTIONS: usize = 256;
const MAX_LINE: u64 = 2 * 1024 * 1024;
const IDLE_TIMEOUT: Duration = Duration::from_secs(300);
const BANNER: &str = "=== RustWallet v1.4.2 ===";
const PROMPT: &[u8] = b"> ";

#[tokio::main]
async fn main() -> std::io::Result<()> {
    let flag_path = std::env::var("FLAG_FILE")
        .unwrap_or_else(|_| "flag.txt".to_string());
    let flag_raw = std::fs::read(&flag_path).map_err(|e| {
        eprintln!("[rustwallet] cannot read {flag_path}: {e}");
        e
    })?;
    let flag: Vec<u8> = flag_raw.into_iter()
        .filter(|&b| b != b'\n' && b != b'\r')
        .collect();

    let port = std::env::args()
        .nth(1)
        .or_else(|| std::env::var("PORT").ok())
        .and_then(|p| p.parse().ok())
        .unwrap_or(DEFAULT_PORT);

    let listener = TcpListener::bind(("0.0.0.0", port)).await?;
    let bank = Arc::new(Mutex::new(Bank::new(&flag)));
    let slots = Arc::new(Semaphore::new(MAX_CONNECTIONS));
    println!("[rustwallet] listening on 0.0.0.0:{port}");

    loop {
        let (stream, _) = match listener.accept().await {
            Ok(c) => c,
            Err(e) => {
                eprintln!("[rustwallet] accept error: {e}");
                continue;
            }
        };
        let Ok(permit) = slots.clone().try_acquire_owned() else {
            let mut stream = stream;
            let _ = stream.write_all(b"ERR server busy\n").await;
            continue;
        };
        let bank = bank.clone();
        tokio::spawn(async move {
            let _ = serve(stream, bank).await;
            drop(permit);
        });
    }
}

async fn serve(stream: TcpStream, bank: Arc<Mutex<Bank>>) -> std::io::Result<()> {
    let (rd, mut wr) = stream.into_split();
    let mut rd = BufReader::new(rd);
    let mut handler = Handler::new(bank);
    let mut buf = Vec::with_capacity(MAX_LINE as usize);

    wr.write_all(format!("{BANNER}\n{MENU}\n").as_bytes()).await?;
    wr.write_all(PROMPT).await?;

    loop {
        buf.clear();
        let n = match timeout(IDLE_TIMEOUT, (&mut rd).take(MAX_LINE + 1).read_until(b'\n', &mut buf)).await {
            Ok(r) => r?,
            Err(_) => {
                wr.write_all(b"\nERR idle timeout\n").await?;
                return Ok(());
            }
        };
        if n == 0 {
            return Ok(());
        }
        if buf.last() != Some(&b'\n') && n as u64 > MAX_LINE {
            wr.write_all(b"ERR line too long\n").await?;
            return Ok(());
        }

        let line = String::from_utf8_lossy(&buf);
        let line = line.trim();

        match handler.handle(line) {
            Reply::Text(text) => {
                if !text.is_empty() {
                    wr.write_all(text.as_bytes()).await?;
                    wr.write_all(b"\n").await?;
                }
                wr.write_all(PROMPT).await?;
            }
            Reply::Close(text) => {
                wr.write_all(text.as_bytes()).await?;
                wr.write_all(b"\n").await?;
                return Ok(());
            }
        }
    }
}
