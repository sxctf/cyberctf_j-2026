

use crate::bank::{fmt_ts, Bank, WalletId};
use base64::prelude::BASE64_STANDARD;
use base64::Engine;
use std::path::PathBuf;
use std::sync::{Arc, Mutex, MutexGuard};

pub const MENU: &str = "\
Commands:
  1. REGISTER <login> <password>
  2. LOGIN <login> <password>
  3. BALANCE <wallet_id>
  4. TRANSFER <to_wallet_id> <amount>
  5. HISTORY <wallet_id>
  6. WHOAMI
  7. UPLOAD <name> <base64>
  8. PLUGIN <name> [args...]
  9. EXIT
  HELP

  Plugin VM (bytecode) ISA: see BYTECODE.md";

#[derive(Default)]
pub struct Session {
    login: Option<String>,
    wallet_id: Option<WalletId>,
}

pub enum Reply {
    Text(String),
    Close(String),
}

pub struct Handler {
    bank: Arc<Mutex<Bank>>,
    session: Session,
}

impl Handler {
    pub fn new(bank: Arc<Mutex<Bank>>) -> Self {
        Handler {
            bank,
            session: Session::default(),
        }
    }

    pub fn handle(&mut self, line: &str) -> Reply {
        let args: Vec<&str> = line.split_whitespace().collect();
        let Some((cmd, args)) = args.split_first() else {
            return Reply::Text(String::new());
        };

        let text = match cmd.to_ascii_uppercase().as_str() {
            "1" | "REGISTER" => self.register(args),
            "2" | "LOGIN" => self.login(args),
            "3" | "BALANCE" => self.balance(args),
            "4" | "TRANSFER" => self.transfer(args),
            "5" | "HISTORY" => self.history(args),
            "6" | "WHOAMI" => self.whoami(),
            "7" | "UPLOAD" => self.upload(args),
            "8" | "PLUGIN" => self.plugin(args),
            "9" | "EXIT" | "QUIT" => return Reply::Close("OK bye".into()),
            "HELP" | "?" => MENU.to_string(),
            _ => "ERR unknown command, type HELP".into(),
        };
        Reply::Text(text)
    }

    fn bank(&self) -> MutexGuard<'_, Bank> {
        self.bank.lock().unwrap_or_else(|e| e.into_inner())
    }

    fn require_login(&self) -> Result<WalletId, String> {
        self.session
            .wallet_id
            .ok_or_else(|| "ERR login required".to_string())
    }

    fn register(&mut self, args: &[&str]) -> String {
        let [login, password] = args else {
            return "ERR usage: REGISTER <login> <password>".into();
        };
        let res = self.bank().register(login, password);
        match res {
            Ok(id) => {
                self.session.login = Some(login.to_string());
                self.session.wallet_id = Some(id);
                format!(
                    "OK registered {login}, wallet_id={id}, balance={}",
                    crate::bank::START_BALANCE
                )
            }
            Err(e) => format!("ERR {}", e.message()),
        }
    }

    fn login(&mut self, args: &[&str]) -> String {
        let [login, password] = args else {
            return "ERR usage: LOGIN <login> <password>".into();
        };
        let res = self.bank().login(login, password);
        match res {
            Ok(id) => {
                self.session.login = Some(login.to_string());
                self.session.wallet_id = Some(id);
                format!("OK logged in as {login}, wallet_id={id}")
            }
            Err(e) => format!("ERR {}", e.message()),
        }
    }

    fn balance(&self, args: &[&str]) -> String {
        let me = match self.require_login() {
            Ok(id) => id,
            Err(e) => return e,
        };
        let [id] = args else {
            return "ERR usage: BALANCE <wallet_id>".into();
        };
        let Ok(id) = id.parse::<WalletId>() else {
            return "ERR bad wallet_id".into();
        };
        let bank = self.bank();
        match bank.wallet(id) {
            Ok(w) if id == me => {
                format!("OK wallet {id} ({}): balance={}", w.owner, w.balance)
            }
            Ok(w) => {
                format!("OK wallet {id} (owner redacted): balance={}", w.balance)
            }
            Err(e) => format!("ERR {}", e.message()),
        }
    }

    fn transfer(&self, args: &[&str]) -> String {
        let from = match self.require_login() {
            Ok(id) => id,
            Err(e) => return e,
        };
        let [to, amount] = args else {
            return "ERR usage: TRANSFER <to_wallet_id> <amount>".into();
        };
        let Ok(to) = to.parse::<WalletId>() else {
            return "ERR bad wallet_id".into();
        };
        let Ok(amount) = amount.parse::<i64>() else {
            return "ERR bad amount".into();
        };
        let res = self.bank().transfer(from, to, amount);
        match res {
            Ok(balance) => format!("OK transferred {amount} to wallet {to}, balance={balance}"),
            Err(e) => format!("ERR {}", e.message()),
        }
    }

    fn history(&self, args: &[&str]) -> String {
        if let Err(e) = self.require_login() {
            return e;
        }
        let [id] = args else {
            return "ERR usage: HISTORY <wallet_id>".into();
        };
        let Ok(id) = id.parse::<WalletId>() else {
            return "ERR bad wallet_id".into();
        };
        let bank = self.bank();
        if let Err(e) = bank.wallet(id) {
            return format!("ERR {}", e.message());
        }
        let txs = bank.history(id);
        let mut out = format!("OK history of wallet {id}, {} entries", txs.len());
        for t in txs {
            out.push_str(&format!(
                "\n  #{:<5} {}  {:>4} -> {:<4} {:>10}  {}",
                t.id,
                fmt_ts(t.ts),
                t.from,
                t.to,
                t.amount,
                t.memo
            ));
        }
        out
    }

    fn whoami(&self) -> String {
        match (&self.session.login, self.session.wallet_id) {
            (Some(login), Some(id)) => format!("OK {login}, wallet_id={id}"),
            _ => "ERR login required".into(),
        }
    }

    fn upload(&self, args: &[&str]) -> String {
        if let Err(e) = self.require_login() {
            return e;
        }
        let [name, data] = args else {
            return "ERR usage: UPLOAD <name> <base64>".into();
        };
        let bytes = match BASE64_STANDARD.decode(data) {
            Ok(b) => b,
            Err(_) => return "ERR bad base64".into(),
        };
        
        let path = format!("plugins/{}.bin", name);
        if let Err(e) = std::fs::write(&path, &bytes) {
            return format!("ERR write {path}: {e}");
        }
        format!("OK uploaded {} bytes → {path}", bytes.len())
    }

    fn plugin(&mut self, args: &[&str]) -> String {
        if let Err(e) = self.require_login() {
            return e;
        }
        let Some((name, rest)) = args.split_first() else {
            return "ERR usage: PLUGIN <name> [args...]".into();
        };
        let path = PathBuf::from(format!("plugins/{}.bin", name));
        let plugin_args = rest.join(" ");
        let bank = self.bank();
        match crate::plugin::load_and_run(&path, &bank, &plugin_args) {
            Ok(s) if s.is_empty() => "OK plugin executed".into(),
            Ok(s) => format!("OK {s}"),
            Err(e) => format!("ERR {e}"),
        }
    }
}