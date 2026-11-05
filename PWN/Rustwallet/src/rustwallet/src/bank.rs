

use crate::auth::{self, Credentials};
use std::collections::{HashMap, VecDeque};
use std::time::{SystemTime, UNIX_EPOCH};

pub const START_BALANCE: i64 = 1000;
pub const MAX_USERS: usize = 5000;
pub const MAX_TX_LOG: usize = 100_000;
pub const HISTORY_PAGE: usize = 50;
pub const GENERATED_WALLETS: usize = 500;
pub const OWNER_BYTES: usize = 32; 

pub type WalletId = u64;

pub struct Wallet {
    pub owner: String,
    pub balance: i64,
}

pub struct User {
    creds: Credentials,
    pub wallet_id: WalletId,
}

pub struct Tx {
    pub id: u64,
    pub ts: u64,
    pub from: WalletId,
    pub to: WalletId,
    pub amount: i64,
    pub memo_from: String,
    pub memo_to: String,
}


pub struct HistoryEntry {
    pub id: u64,
    pub ts: u64,
    pub from: WalletId,
    pub to: WalletId,
    pub amount: i64,
    pub memo: String,
}

#[derive(Clone)]
pub struct SearchHit {
    pub wallet_id: WalletId,
    pub tx_id: u64,
    pub ts: u64,
    pub from: WalletId,
    pub to: WalletId,
    pub amount: i64,
    pub memo: String,
}

#[derive(Debug)]
pub enum BankError {
    LoginTaken,
    BadLogin,
    BadPassword,
    TooManyUsers,
    InvalidCredentials,
    WalletNotFound,
    InsufficientFunds,
    AmountOutOfRange,
}

impl BankError {
    pub fn message(&self) -> String {
        match self {
            BankError::LoginTaken => "login already taken".into(),
            BankError::BadLogin => format!(
                "login must be {}-{} chars [A-Za-z0-9_]",
                auth::LOGIN_MIN, auth::LOGIN_MAX
            ),
            BankError::BadPassword => format!(
                "password must be {}-{} printable chars",
                auth::PASSWORD_MIN, auth::PASSWORD_MAX
            ),
            BankError::TooManyUsers => "registration closed: user limit reached".into(),
            BankError::InvalidCredentials => "invalid credentials".into(),
            BankError::WalletNotFound => "wallet not found".into(),
            BankError::InsufficientFunds => "insufficient funds".into(),
            BankError::AmountOutOfRange => "amount out of range".into(),
        }
    }
}

pub struct Bank {
    users: HashMap<String, User>,
    wallets: HashMap<WalletId, Wallet>,
    txs: VecDeque<Tx>,
    next_wallet: WalletId,
    next_tx: u64,
    flag: Vec<u8>,
}

impl Bank {
    pub fn new(flag: &[u8]) -> Self {
        let mut bank = Bank {
            users: HashMap::new(),
            wallets: HashMap::new(),
            txs: VecDeque::new(),
            next_wallet: 1,
            next_tx: 1,
            flag: flag.to_vec(),
        };
        bank.seed_system();
        bank.seed_generated();
        bank.plant_decoy();
        bank
    }

    pub fn max_wallet_id(&self) -> WalletId {
        self.next_wallet.saturating_sub(1)
    }

    
    pub fn flag_bytes(&self) -> &[u8] {
        &self.flag
    }

    
    
    pub fn all_balances(&self) -> Vec<i64> {
        let mut ids: Vec<WalletId> = self.wallets.keys().copied().collect();
        ids.sort_unstable();
        ids.into_iter()
            .filter_map(|id| self.wallets.get(&id).map(|w| w.balance))
            .collect()
    }

    
    
    pub fn search_all(&self, needle: &str) -> Vec<SearchHit> {
        let mut out = Vec::new();
        for t in self.txs.iter().rev() {
            if t.memo_from.contains(needle) {
                out.push(SearchHit {
                    wallet_id: t.from,
                    tx_id: t.id,
                    ts: t.ts,
                    from: t.from,
                    to: t.to,
                    amount: t.amount,
                    memo: t.memo_from.clone(),
                });
            }
            if t.memo_to.contains(needle) {
                out.push(SearchHit {
                    wallet_id: t.to,
                    tx_id: t.id,
                    ts: t.ts,
                    from: t.from,
                    to: t.to,
                    amount: t.amount,
                    memo: t.memo_to.clone(),
                });
            }
        }
        out
    }

    pub fn register(&mut self, login: &str, password: &str) -> Result<WalletId, BankError> {
        if !auth::valid_login(login) {
            return Err(BankError::BadLogin);
        }
        if !auth::valid_password(password) {
            return Err(BankError::BadPassword);
        }
        if self.users.contains_key(login) {
            return Err(BankError::LoginTaken);
        }
        if self.users.len() >= MAX_USERS {
            return Err(BankError::TooManyUsers);
        }
        Ok(self.create_account(login, password, START_BALANCE))
    }

    pub fn login(&self, login: &str, password: &str) -> Result<WalletId, BankError> {
        match self.users.get(login) {
            Some(u) if u.creds.verify(password) => Ok(u.wallet_id),
            _ => Err(BankError::InvalidCredentials),
        }
    }

    pub fn wallet(&self, id: WalletId) -> Result<&Wallet, BankError> {
        self.wallets.get(&id).ok_or(BankError::WalletNotFound)
    }

    pub fn transfer(&mut self, from: WalletId, to: WalletId, amount: i64) -> Result<i64, BankError> {
        let from_balance = self.wallet(from)?.balance;
        let to_balance = self.wallet(to)?.balance;
        if amount > from_balance {
            return Err(BankError::InsufficientFunds);
        }
        let new_from = from_balance
            .checked_sub(amount)
            .ok_or(BankError::AmountOutOfRange)?;
        let new_to = to_balance
            .checked_add(amount)
            .ok_or(BankError::AmountOutOfRange)?;
        if let Some(w) = self.wallets.get_mut(&from) {
            w.balance = new_from;
        }
        if let Some(w) = self.wallets.get_mut(&to) {
            w.balance = new_to;
        }
        self.log_tx(now(), from, to, amount, "p2p transfer", "p2p transfer");
        Ok(self.wallet(from)?.balance)
    }

    
    pub fn history(&self, viewer: WalletId) -> Vec<HistoryEntry> {
        let mut out: Vec<HistoryEntry> = self
            .txs
            .iter()
            .rev()
            .filter(|t| t.from == viewer || t.to == viewer)
            .take(HISTORY_PAGE)
            .map(|t| HistoryEntry {
                id: t.id,
                ts: t.ts,
                from: t.from,
                to: t.to,
                amount: t.amount,
                memo: if t.from == viewer {
                    t.memo_from.clone()
                } else {
                    t.memo_to.clone()
                },
            })
            .collect();
        out.reverse();
        out
    }

    fn create_account(&mut self, login: &str, password: &str, balance: i64) -> WalletId {
        let id = self.next_wallet;
        self.next_wallet += 1;
        self.wallets.insert(
            id,
            Wallet {
                owner: login.to_string(),
                balance,
            },
        );
        self.users.insert(
            login.to_string(),
            User {
                creds: Credentials::new(password),
                wallet_id: id,
            },
        );
        id
    }

    fn create_wallet(&mut self, owner: String, balance: i64) -> WalletId {
        let id = self.next_wallet;
        self.next_wallet += 1;
        self.wallets.insert(id, Wallet { owner, balance });
        id
    }

    fn log_tx(
        &mut self,
        ts: u64,
        from: WalletId,
        to: WalletId,
        amount: i64,
        memo_from: &str,
        memo_to: &str,
    ) {
        if self.txs.len() >= MAX_TX_LOG {
            self.txs.pop_front();
        }
        self.txs.push_back(Tx {
            id: self.next_tx,
            ts,
            from,
            to,
            amount,
            memo_from: memo_from.to_string(),
            memo_to: memo_to.to_string(),
        });
        self.next_tx += 1;
    }

    fn seed_system(&mut self) {
        const ACCOUNTS: &[(&str, i64)] = &[
            ("treasury", 7_412_500),
            ("payroll", 64_300),
            ("admin", 91_750),
            ("cold_storage", 5_000_000),
            ("alice", 2_480),
            ("bob", 305),
        ];
        for (login, balance) in ACCOUNTS {
            let pw = auth::random_password();
            self.create_account(login, &pw, *balance);
        }

        
        const T0: u64 = 1_788_253_200;
        const H: u64 = 3600;
        const D: u64 = 24 * H;
        let history: &[(u64, WalletId, WalletId, i64, &str)] = &[
            (T0, 1, 4, 5_000_000, "Move reserves to cold storage (ticket OPS-1142)"),
            (T0 + 2 * H, 1, 2, 250_000, "Payroll funding: September"),
            (T0 + D, 2, 3, 18_000, "Salary 09/2026: admin"),
            (T0 + D + 5 * 60, 2, 5, 4_200, "Salary 09/2026: alice"),
            (T0 + D + 6 * 60, 2, 6, 3_900, "Salary 09/2026: bob"),
            (T0 + 2 * D, 1, 3, 50_000, "Bonus, approved by CFO. CONFIDENTIAL, do not disclose"),
            (T0 + 2 * D + H, 3, 1, 1, "test transfer"),
            (T0 + 3 * D, 5, 6, 150, "pizza + taxi"),
            (T0 + 4 * D, 6, 5, 20, "thx"),
            (T0 + 5 * D, 3, 6, 2_500, "cash out via bob, don't log it in the report"),
            (T0 + 6 * D, 1, 2, 125_000, "Payroll top-up"),
            (T0 + 7 * D, 4, 1, 400_000, "Emergency liquidity (approved: admin)"),
        ];
        for (ts, from, to, amount, memo) in history {
            self.log_tx(*ts, *from, *to, *amount, memo, memo);
        }
    }

    fn seed_generated(&mut self) {
        let mut rng = Rng::new();
        const T0: u64 = 1_788_253_200;
        const D: u64 = 86_400;

        let mut ids = Vec::with_capacity(GENERATED_WALLETS);
        for _ in 0..GENERATED_WALLETS {
            let owner = random_owner();
            let id = self.create_wallet(owner, 0);
            ids.push(id);
        }

        for &id in &ids {
            let t_fund = T0 + 10 * D + rng.range(0, 30 * D);
            let initial = rng.range(200, 20_000) as i64;
            self.log_tx(t_fund, 1, id, initial, "outgoing funding", "incoming funding");
            self.wallets.get_mut(&id).unwrap().balance += initial;

            let n = rng.range(2, 6);
            for _ in 0..n {
                let ts = t_fund + rng.range(0, 60 * D);
                let cp = ids[rng.range(0, ids.len() as u64) as usize];
                if cp == id {
                    continue;
                }
                let amount = rng.range(5, 1_500) as i64;
                let (m_from, m_to) = mundane_memo(rng.range(0, 8) as usize);
                if rng.range(0, 2) == 0 {
                    self.log_tx(ts, cp, id, amount, m_from, m_to);
                    self.wallets.get_mut(&id).unwrap().balance += amount;
                    self.wallets.get_mut(&cp).unwrap().balance -= amount;
                } else {
                    let bal = self.wallets.get(&id).unwrap().balance;
                    if bal < amount {
                        continue;
                    }
                    self.log_tx(ts, id, cp, amount, m_from, m_to);
                    self.wallets.get_mut(&id).unwrap().balance -= amount;
                    self.wallets.get_mut(&cp).unwrap().balance += amount;
                }
            }
        }
    }

    
    
    
    
    fn plant_decoy(&mut self) {
        let mut rng = Rng::new();
        const T0: u64 = 1_788_253_200;
        const D: u64 = 86_400;

        let gen_ids: Vec<WalletId> = self
            .wallets
            .keys()
            .copied()
            .filter(|&id| id > 6)
            .collect();
        if gen_ids.is_empty() {
            return;
        }
        let fake_id = gen_ids[rng.range(0, gen_ids.len() as u64) as usize];
        let fake_key = fake_id.to_le_bytes();
        let fake_plain = b"FLAG{wrong_key_ha_ha}";
        let fake_ct: Vec<u8> = fake_plain
            .iter()
            .enumerate()
            .map(|(i, &b)| b ^ fake_key[i % fake_key.len()])
            .collect();
        let fake_memo = format!("enc:v0:{}", hex_encode(&fake_ct));
        self.log_tx(T0 + 90 * D, 1, fake_id, 1, "outgoing payment", &fake_memo);
    }
}

fn random_owner() -> String {
    let bytes = rand_bytes::<OWNER_BYTES>();
    format!("u_{}", hex_encode(&bytes))
}

fn hex_encode(b: &[u8]) -> String {
    let mut s = String::with_capacity(b.len() * 2);
    for byte in b {
        s.push_str(&format!("{:02x}", byte));
    }
    s
}

fn mundane_memo(i: usize) -> (&'static str, &'static str) {
    const MEMOS: &[(&str, &str)] = &[
        ("outgoing payment", "incoming payment"),
        ("invoice settled", "invoice received"),
        ("subscription", "subscription"),
        ("refund issued", "refund received"),
        ("consulting fee", "consulting income"),
        ("utility bill", "utility credit"),
        ("goods delivery", "goods received"),
        ("transfer", "transfer"),
    ];
    MEMOS[i % MEMOS.len()]
}

fn rand_bytes<const N: usize>() -> [u8; N] {
    let mut buf = [0u8; N];
    auth::random_bytes(&mut buf);
    buf
}

struct Rng {
    state: u64,
}

impl Rng {
    fn new() -> Self {
        Rng {
            state: u64::from_le_bytes(rand_bytes::<8>()) | 1,
        }
    }

    fn next(&mut self) -> u64 {
        self.state ^= self.state << 13;
        self.state ^= self.state >> 7;
        self.state ^= self.state << 17;
        self.state
    }

    fn range(&mut self, lo: u64, hi: u64) -> u64 {
        if hi <= lo {
            return lo;
        }
        lo + self.next() % (hi - lo)
    }
}

pub fn now() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

pub fn fmt_ts(ts: u64) -> String {
    let days = (ts / 86_400) as i64;
    let secs = ts % 86_400;
    let z = days + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    let y = yoe + era * 400 + if m <= 2 { 1 } else { 0 };
    format!(
        "{:04}-{:02}-{:02} {:02}:{:02}",
        y,
        m,
        d,
        secs / 3600,
        (secs % 3600) / 60
    )
}