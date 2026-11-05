

use sha2::{Digest, Sha256};
use std::fs::File;
use std::io::Read;

pub const LOGIN_MIN: usize = 3;
pub const LOGIN_MAX: usize = 16;
pub const PASSWORD_MIN: usize = 4;
pub const PASSWORD_MAX: usize = 64;

pub struct Credentials {
    salt: [u8; 16],
    hash: [u8; 32],
}

impl Credentials {
    pub fn new(password: &str) -> Self {
        let mut salt = [0u8; 16];
        random_bytes(&mut salt);
        let hash = digest(&salt, password);
        Credentials { salt, hash }
    }

    pub fn verify(&self, password: &str) -> bool {
        ct_eq(&self.hash, &digest(&self.salt, password))
    }
}

pub fn random_password() -> String {
    let mut buf = [0u8; 24];
    random_bytes(&mut buf);
    buf.iter().map(|b| format!("{:02x}", b)).collect()
}

pub fn valid_login(login: &str) -> bool {
    (LOGIN_MIN..=LOGIN_MAX).contains(&login.len())
        && login.bytes().all(|c| c.is_ascii_alphanumeric() || c == b'_')
}

pub fn valid_password(password: &str) -> bool {
    (PASSWORD_MIN..=PASSWORD_MAX).contains(&password.len())
        && password.bytes().all(|c| c.is_ascii_graphic())
}

fn digest(salt: &[u8], password: &str) -> [u8; 32] {
    let mut h = Sha256::new();
    h.update(salt);
    h.update(password.as_bytes());
    h.finalize().into()
}

fn ct_eq(a: &[u8], b: &[u8]) -> bool {
    a.len() == b.len() && a.iter().zip(b).fold(0u8, |acc, (x, y)| acc | (x ^ y)) == 0
}

pub(crate) fn random_bytes(buf: &mut [u8]) {
    File::open("/dev/urandom")
        .and_then(|mut f| f.read_exact(buf))
        .expect("cannot read /dev/urandom");
}
