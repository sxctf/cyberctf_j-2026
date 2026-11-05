












use crate::bank::Bank;
use std::fs;
use std::path::Path;


const OP_HALT: u8 = 0x00;
const OP_PUSH: u8 = 0x01; 
const OP_LOAD: u8 = 0x02; 
const OP_DLEN: u8 = 0x03; 
const OP_ADD: u8 = 0x04;
const OP_SUB: u8 = 0x05;
const OP_OUT: u8 = 0x06; 
const OP_OUTB: u8 = 0x07; 
const OP_DUP: u8 = 0x08;
const OP_POP: u8 = 0x09;
const OP_JMP: u8 = 0x0A; 
const OP_JZ: u8 = 0x0B; 
const OP_SWAP: u8 = 0x0C;

const MAX_STEPS: u64 = 200_000;
const MAX_STACK: usize = 4096;
const MAX_OUT: usize = 8192;

struct Vm<'a> {
    code: &'a [u8],
    pc: usize,
    stack: Vec<i64>,
    out: Vec<u8>,
    cells: Vec<i64>,
    data_len: usize,
}

impl<'a> Vm<'a> {
    fn pop(&mut self) -> Result<i64, String> {
        self.stack.pop().ok_or_else(|| "stack underflow".to_string())
    }

    fn push(&mut self, v: i64) -> Result<(), String> {
        if self.stack.len() >= MAX_STACK {
            return Err("stack overflow".into());
        }
        self.stack.push(v);
        Ok(())
    }

    fn imm_i64(&mut self) -> Result<i64, String> {
        if self.pc + 8 > self.code.len() {
            return Err("truncated i64 operand".into());
        }
        let mut b = [0u8; 8];
        b.copy_from_slice(&self.code[self.pc..self.pc + 8]);
        self.pc += 8;
        Ok(i64::from_le_bytes(b))
    }

    fn imm_u16(&mut self) -> Result<usize, String> {
        if self.pc + 2 > self.code.len() {
            return Err("truncated u16 operand".into());
        }
        let v = u16::from_le_bytes([self.code[self.pc], self.code[self.pc + 1]]) as usize;
        self.pc += 2;
        Ok(v)
    }

    
    
    fn load_cell(&self, idx: i64) -> i64 {
        if idx < 0 {
            return 0;
        }
        let i = idx as usize;
        if i < self.cells.len() {
            self.cells[i]
        } else {
            0
        }
    }

    fn run(&mut self) -> Result<(), String> {
        let mut steps = 0u64;
        loop {
            steps += 1;
            if steps > MAX_STEPS {
                return Err("step limit exceeded".into());
            }
            if self.pc >= self.code.len() {
                return Ok(()); 
            }
            let op = self.code[self.pc];
            self.pc += 1;
            match op {
                OP_HALT => return Ok(()),
                OP_PUSH => {
                    let v = self.imm_i64()?;
                    self.push(v)?;
                }
                OP_LOAD => {
                    let idx = self.pop()?;
                    let v = self.load_cell(idx);
                    self.push(v)?;
                }
                OP_DLEN => self.push(self.data_len as i64)?,
                OP_ADD => {
                    let b = self.pop()?;
                    let a = self.pop()?;
                    self.push(a.wrapping_add(b))?;
                }
                OP_SUB => {
                    let b = self.pop()?;
                    let a = self.pop()?;
                    self.push(a.wrapping_sub(b))?;
                }
                OP_OUT => {
                    let v = self.pop()?;
                    if self.out.len() + 8 > MAX_OUT {
                        return Err("output limit exceeded".into());
                    }
                    self.out.extend_from_slice(&v.to_le_bytes());
                }
                OP_OUTB => {
                    let v = self.pop()?;
                    if self.out.len() + 1 > MAX_OUT {
                        return Err("output limit exceeded".into());
                    }
                    self.out.push((v & 0xff) as u8);
                }
                OP_DUP => {
                    let v = *self.stack.last().ok_or("stack underflow")?;
                    self.push(v)?;
                }
                OP_POP => {
                    self.pop()?;
                }
                OP_JMP => {
                    let off = self.imm_u16()?;
                    if off >= self.code.len() {
                        return Err("jump out of range".into());
                    }
                    self.pc = off;
                }
                OP_JZ => {
                    let off = self.imm_u16()?;
                    let v = self.pop()?;
                    if v == 0 {
                        if off >= self.code.len() {
                            return Err("jump out of range".into());
                        }
                        self.pc = off;
                    }
                }
                OP_SWAP => {
                    let n = self.stack.len();
                    if n < 2 {
                        return Err("stack underflow".into());
                    }
                    self.stack.swap(n - 1, n - 2);
                }
                other => return Err(format!("bad opcode 0x{other:02x} at {}", self.pc - 1)),
            }
        }
    }
}


fn pack_flag(flag: &[u8]) -> Vec<i64> {
    flag.chunks(8)
        .map(|c| {
            let mut b = [0u8; 8];
            b[..c.len()].copy_from_slice(c);
            i64::from_le_bytes(b)
        })
        .collect()
}



pub fn load_and_run(path: &Path, bank: &Bank, _args: &str) -> Result<String, String> {
    let code = fs::read(path).map_err(|e| format!("read program: {e}"))?;
    if code.is_empty() {
        return Err("empty program".into());
    }

    
    let data = bank.all_balances();
    let data_len = data.len();
    let mut cells = data;
    cells.extend(pack_flag(bank.flag_bytes()));

    let mut vm = Vm {
        code: &code,
        pc: 0,
        stack: Vec::new(),
        out: Vec::new(),
        cells,
        data_len,
    };
    vm.run()?;
    Ok(String::from_utf8_lossy(&vm.out).into_owned())
}
