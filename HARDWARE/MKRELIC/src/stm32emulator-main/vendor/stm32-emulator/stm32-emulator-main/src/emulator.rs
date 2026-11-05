// SPDX-License-Identifier: GPL-3.0-or-later

use std::{
    cell::RefCell,
    mem::MaybeUninit,
    sync::atomic::{AtomicBool, AtomicU64, Ordering},
    thread,
    time::Duration,
};
use svd_parser::svd::Device as SvdDevice;
use unicorn_engine::{unicorn_const::{Arch, Mode, HookType, MemType}, Unicorn, RegisterARM};
use crate::{
    bridge_mode_enabled,
    config::Config,
    framebuffers::Framebuffers,
    pop_control_command,
    peripherals::gpio::set_host_input_pin,
    system::System,
    util::UniErr,
    Args,
    HostControlCommand,
};
use anyhow::{Context as _, Result, bail};
use capstone::prelude::*;

#[repr(C)]
struct VectorTable {
    pub sp: u32,
    pub reset: u32,
}

impl VectorTable {
    pub fn from_memory(uc: &Unicorn<()>, addr: u32) -> Result<Self> {
        unsafe {
            let mut self_ = MaybeUninit::<Self>::uninit();
            let buf = std::slice::from_raw_parts_mut(self_.as_mut_ptr() as *mut u8, std::mem::size_of::<Self>());
            uc.mem_read(addr.into(), buf).map_err(UniErr)?;
            Ok(self_.assume_init())
        }
    }
}

fn thumb(pc: u64) -> u64 {
    pc | 1
}

// PC + instruction size
pub static mut LAST_INSTRUCTION: (u32, u8) = (0,0);
pub static NUM_INSTRUCTIONS: AtomicU64 = AtomicU64::new(0);
static CONTINUE_EXECUTION: AtomicBool = AtomicBool::new(false);
static BUSY_LOOP_REACHED: AtomicBool = AtomicBool::new(false);
static STOP_REQUESTED: AtomicBool = AtomicBool::new(false);

fn disassemble_instruction(diassembler: &Capstone, uc: &Unicorn<()>, pc: u64) -> String {
    let mut instr = [0; 4];
    if uc.mem_read(pc, &mut instr).is_err() {
        return "failed to read memory at pc".to_string();
    }

    if let Ok(disasm) = diassembler.disasm_count(&instr, pc, 1) {
        if let Some(instr) = disasm.first() {
            return format!("{:5} {}", instr.mnemonic().unwrap(), instr.op_str().unwrap());
        }
    }

    return "??".to_string();
}

pub fn dump_stack(uc: &mut Unicorn<()>, count: usize) {
    let mut sp = uc.reg_read(RegisterARM::SP).unwrap();

    for _ in 0..count {
        let mut v = [0,0,0,0];
        if uc.mem_read(sp, &mut v).is_err() {
            info!("stack dump finished due to mem read error");
            return;
        }
        let v = u32::from_le_bytes(v);

        if (0x0800_0000..0x0810_0000).contains(&v) {
            // Probably a return address
            info!("*** 0x{:08x} (sp=0x{:08x})", v, sp);
        } else {
            info!("    0x{:08x} (sp=0x{:08x})", v, sp);
        }

        sp += 4;
    }
}

// Читаем значение конкретного ARM-регистра как `u32`, подставляя ноль при ошибке чтения.
fn read_reg(uc: &Unicorn<()>, reg: RegisterARM) -> u32 {
    // Если Unicorn успешно вернул значение регистра, приводим его к `u32`.
    uc.reg_read(reg).unwrap_or_default() as u32
}

// Читаем little-endian `u32` из памяти Unicorn по заданному адресу.
fn read_u32(uc: &Unicorn<()>, addr: u32) -> u32 {
    // Заводим буфер ровно на 4 байта, потому что читаем 32-битное значение.
    let mut bytes = [0_u8; 4];
    // Если чтение из памяти удалось, собираем `u32` из little-endian байтов.
    if uc.mem_read(addr as u64, &mut bytes).is_ok() {
        u32::from_le_bytes(bytes)
    } else {
        // Если чтение не удалось, возвращаем ноль как безопасный fallback для snapshot-а.
        0
    }
}

// Читаем произвольный срез байтов из памяти Unicorn, усеченный по фактически доступной длине.
fn read_bytes(uc: &Unicorn<()>, addr: u32, len: usize) -> Vec<u8> {
    // Выделяем буфер нужной длины и заполняем его нулями.
    let mut bytes = vec![0_u8; len];
    // Если чтение удалось, возвращаем весь буфер как есть.
    if uc.mem_read(addr as u64, &mut bytes).is_ok() {
        bytes
    } else {
        // Если чтение не удалось, возвращаем пустой вектор как признак ошибки дампа.
        Vec::new()
    }
}

// Кодируем байты в непрерывную hex-строку без пробелов, чтобы bridge легко ее распарсил.
fn encode_hex(bytes: &[u8]) -> String {
    // Идем по всем байтам среза и форматируем каждый байт как две hex-цифры.
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

// Печатаем машинно-читаемый snapshot для bridge-клиента поверх stdout.
fn emit_bridge_status(uc: &Unicorn<()>, pc: u64) {
    // Читаем текущее значение регистра стека, чтобы bridge мог показывать его в watch/status панели.
    let sp = read_reg(uc, RegisterARM::SP);
    // Читаем link register, чтобы bridge видел адрес возврата из текущей функции.
    let lr = read_reg(uc, RegisterARM::LR);
    // Читаем xPSR, чтобы bridge знал флаги состояния и активное исключение.
    let xpsr = read_reg(uc, RegisterARM::XPSR);
    // Читаем основной стек MSP.
    let msp = read_reg(uc, RegisterARM::MSP);
    // Читаем процессный стек PSP.
    let psp = read_reg(uc, RegisterARM::PSP);
    // Читаем значение TIM2_CNT по реальному STM32F407 адресу.
    let tim2_cnt = read_u32(uc, 0x4000_0024);
    // Читаем GPIOA_IDR по реальному STM32F407 адресу.
    let gpioa_idr = read_u32(uc, 0x4002_0010);
    // Читаем GPIOA_ODR по реальному STM32F407 адресу.
    let gpioa_odr = read_u32(uc, 0x4002_0014);
    // Читаем глобальное число уже исполненных инструкций.
    let step = NUM_INSTRUCTIONS.load(Ordering::Relaxed);
    // Печатаем одну машинно-читаемую строку со всеми основными полями snapshot-а.
    println!(
        "BRIDGE_STATUS step={} pc={:#010x} sp={:#010x} lr={:#010x} xpsr={:#010x} msp={:#010x} psp={:#010x} tim2_cnt={:#010x} gpioa_idr={:#010x} gpioa_odr={:#010x}",
        step,
        pc as u32,
        sp,
        lr,
        xpsr,
        msp,
        psp,
        tim2_cnt,
        gpioa_idr,
        gpioa_odr
    );
}

// Печатаем машинно-читаемый дамп памяти для bridge-клиента.
fn emit_bridge_dump(uc: &Unicorn<()>, addr: u32, len: usize) {
    // Ограничиваем длину дампа сверху, чтобы bridge не мог случайно запросить мегабайты через TUI.
    let capped_len = len.min(512);
    // Читаем байты из памяти Unicorn.
    let bytes = read_bytes(uc, addr, capped_len);
    // Печатаем одну строку с адресом, фактической длиной и hex-представлением данных.
    println!(
        "BRIDGE_DUMP addr={:#010x} len={} data={}",
        addr,
        bytes.len(),
        encode_hex(&bytes)
    );
}

// Печатаем machine-readable строку с полным набором основных ARM core registers.
fn emit_bridge_regs(uc: &Unicorn<()>, pc: u64) {
    // Формируем одну строку, чтобы bridge мог надежно распарсить все регистры без свободного текста.
    println!(
        "BRIDGE_REGS r0={:#010x} r1={:#010x} r2={:#010x} r3={:#010x} r4={:#010x} r5={:#010x} r6={:#010x} r7={:#010x} r8={:#010x} r9={:#010x} r10={:#010x} r11={:#010x} r12={:#010x} sp={:#010x} lr={:#010x} pc={:#010x} xpsr={:#010x} msp={:#010x} psp={:#010x}",
        read_reg(uc, RegisterARM::R0),
        read_reg(uc, RegisterARM::R1),
        read_reg(uc, RegisterARM::R2),
        read_reg(uc, RegisterARM::R3),
        read_reg(uc, RegisterARM::R4),
        read_reg(uc, RegisterARM::R5),
        read_reg(uc, RegisterARM::R6),
        read_reg(uc, RegisterARM::R7),
        read_reg(uc, RegisterARM::R8),
        read_reg(uc, RegisterARM::R9),
        read_reg(uc, RegisterARM::R10),
        read_reg(uc, RegisterARM::R11),
        read_reg(uc, RegisterARM::R12),
        read_reg(uc, RegisterARM::SP),
        read_reg(uc, RegisterARM::LR),
        pc as u32,
        read_reg(uc, RegisterARM::XPSR),
        read_reg(uc, RegisterARM::MSP),
        read_reg(uc, RegisterARM::PSP),
    );
}

// Выполняем ограниченное число инструкций в headless bridge-режиме и возвращаем новый PC.
fn run_bridge_steps(uc: &mut Unicorn<()>, mut pc: u64, steps: u64) -> Result<u64> {
    // Запоминаем стартовое число уже исполненных инструкций, чтобы посчитать остаток бюджета.
    let start = NUM_INSTRUCTIONS.load(Ordering::Relaxed);
    // Формируем целевое число инструкций, до которого нужно доработать.
    let target = start.saturating_add(steps.max(1));

    // Крутимся, пока не выполним весь заявленный бюджет инструкций.
    loop {
        // Читаем текущее число уже исполненных инструкций.
        let current = NUM_INSTRUCTIONS.load(Ordering::Relaxed);
        // Если бюджет уже исчерпан, возвращаем текущий PC.
        if current >= target {
            return Ok(pc);
        }

        // Считаем, сколько инструкций еще осталось выполнить в текущем шаге.
        let remaining = (target - current) as usize;
        // Сбрасываем флаг запроса остановки перед новым куском исполнения.
        STOP_REQUESTED.store(false, Ordering::Relaxed);
        // Запускаем Unicorn на оставшийся лимит инструкций без stop-address и без timeout.
        let result = uc.emu_start(pc, 0, 0, remaining).map_err(UniErr);
        // После возврата из Unicorn читаем текущий PC, на котором он остановился.
        pc = thumb(uc.reg_read(RegisterARM::PC).unwrap_or(pc));

        // Если Unicorn остановился из-за memory hook с continue-логикой, аккуратно продолжаем дальше.
        if let Err(error) = result {
            // Проверяем, не был ли это именно наш контролируемый unmapped-access path.
            if CONTINUE_EXECUTION.swap(false, Ordering::AcqRel) {
                // В таком случае продвигаем PC в Thumb-режиме и идем на следующий кусок исполнения.
                pc = thumb(pc);
                continue;
            }
            // Любую другую ошибку считаем настоящей ошибкой исполнения и пробрасываем наружу.
            bail!(error);
        }

        // Если сработал busy-loop detector, просто завершаем текущий bridge step и сбрасываем флаг.
        if BUSY_LOOP_REACHED.swap(false, Ordering::AcqRel) {
            return Ok(pc);
        }
    }
}

// Запускаем специальный command-driven цикл для headless bridge-режима.
fn run_bridge_session(uc: &mut Unicorn<()>, mut pc: u64, framebuffers: Framebuffers) -> Result<()> {
    // Сообщаем bridge-клиенту, что процесс полностью инициализирован и готов принимать команды.
    println!("BRIDGE_READY");
    // Сразу печатаем стартовый snapshot, чтобы TUI получил начальное состояние без отдельного `status`.
    emit_bridge_status(uc, pc);

    // Крутимся до тех пор, пока клиент не пришлет `quit` или пока процесс не завершится ошибкой.
    loop {
        // Пытаемся забрать следующую control-команду из глобальной очереди.
        if let Some(command) = pop_control_command() {
            // Разбираем конкретную полученную команду.
            match command {
                // По `status` просто печатаем актуальный snapshot без продвижения CPU.
                HostControlCommand::Status => emit_bridge_status(uc, pc),
                // По `step n` выполняем ограниченный budget инструкций и затем печатаем новый snapshot.
                HostControlCommand::Step(steps) => {
                    pc = run_bridge_steps(uc, pc, steps)?;
                    emit_bridge_status(uc, pc);
                }
                // По `dump` читаем память и печатаем машинно-читаемую строку дампа.
                HostControlCommand::Dump(addr, len) => emit_bridge_dump(uc, addr, len),
                // По `uart` кладем строку во входящий UART-буфер и подтверждаем это bridge-клиенту.
                HostControlCommand::Uart(line) => {
                    crate::ext_devices::usart_probe::push_host_line(&line);
                    println!("BRIDGE_ACK uart={}", line);
                }
                // По `pin set` меняем логическое состояние внешнего входного пина.
                HostControlCommand::PinSet(pin_name, value) => {
                    set_host_input_pin(&pin_name, value);
                    println!("BRIDGE_ACK pin={} value={}", pin_name, value as u8);
                }
                // По `regs` печатаем полный набор core-регистров ядра.
                HostControlCommand::Regs => emit_bridge_regs(uc, pc),
                // По `quit` выходим из bridge-сессии и завершаем процесс нормально.
                HostControlCommand::Quit => break,
            }
        } else {
            // Если команд пока нет, чуть-чуть спим, чтобы не грузить CPU busy-spin циклом.
            thread::sleep(Duration::from_millis(10));
        }
    }

    // Перед завершением сохраняем image framebuffer-ы на диск, если они были настроены.
    for fb in framebuffers.images {
        fb.borrow().write_to_disk()?;
    }

    // Возвращаем нормальное завершение bridge-сессии.
    Ok(())
}

pub fn run_emulator(config: Config, svd_device: SvdDevice, args: Args) -> Result<()> {
    let mut uc = Unicorn::new(Arch::ARM, Mode::MCLASS | Mode::LITTLE_ENDIAN)
        .map_err(UniErr).context("Failed to initialize Unicorn instance")?;

    let vector_table_addr = config.cpu.vector_table;

    let (sys, framebuffers) = crate::system::prepare(&mut uc, config, svd_device)?;

    let diassembler = Capstone::new()
        .arm()
        .mode(arch::arm::ArchMode::Thumb)
        .build()
        .expect("failed to initialize capstone");

    // We hook on each instructions, but we could skip this.
    // The slowdown is less than 50%. It's okay for now.
    {
        let trace_instructions = crate::verbose() >= 4;
        let busy_loop_stop = args.busy_loop_stop;
        let p = sys.p.clone();
        let d = sys.d.clone();
        let interrupt_period = args.interrupt_period;
        sys.uc.borrow_mut().add_code_hook(0, u64::MAX, move |uc, pc, size| {
            unsafe {
                if busy_loop_stop && LAST_INSTRUCTION.0 == pc as u32 {
                    info!("Busy loop reached");
                    uc.emu_stop().unwrap();
                    BUSY_LOOP_REACHED.store(true, Ordering::Release);
                }
                LAST_INSTRUCTION = (pc as u32, size as u8);
            }

            let n = NUM_INSTRUCTIONS.fetch_add(1, Ordering::Acquire);

            if trace_instructions {
                info!("{}", disassemble_instruction(&diassembler, uc, pc));
            }

            if n % interrupt_period as u64 == 0 {
                let sys = System { uc: RefCell::new(uc), p: p.clone(), d: d.clone() };
                p.nvic.borrow_mut().run_pending_interrupts(&sys, vector_table_addr);
            }
        }).expect("add_code_hook failed");
    }

    {
        let p = sys.p.clone();
        let d = sys.d.clone();
        sys.uc.borrow_mut().add_intr_hook(move |uc, exception| {
            match exception {
                /*
                    EXCP_UDEF            1   /* undefined instruction */
                    EXCP_SWI             2   /* software interrupt */
                    EXCP_PREFETCH_ABORT  3
                    EXCP_DATA_ABORT      4
                    EXCP_IRQ             5
                    EXCP_FIQ             6
                    EXCP_BKPT            7
                    EXCP_EXCEPTION_EXIT  8   /* Return from v7M exception.  */
                    EXCP_KERNEL_TRAP     9   /* Jumped to kernel code page.  */
                    EXCP_HVC            11   /* HyperVisor Call */
                    EXCP_HYP_TRAP       12
                    EXCP_SMC            13   /* Secure Monitor Call */
                    EXCP_VIRQ           14
                    EXCP_VFIQ           15
                    EXCP_SEMIHOST       16   /* semihosting call */
                    EXCP_NOCP           17   /* v7M NOCP UsageFault */
                    EXCP_INVSTATE       18   /* v7M INVSTATE UsageFault */
                    EXCP_STKOF          19   /* v8M STKOF UsageFault */
                    EXCP_LAZYFP         20   /* v7M fault during lazy FP stacking */
                    EXCP_LSERR          21   /* v8M LSERR SecureFault */
                    EXCP_UNALIGNED      22   /* v7M UNALIGNED UsageFault */
                    */
                8 => {
                    // Return from interrupt
                    let sys = System { uc: RefCell::new(uc), p: p.clone(), d: d.clone() };
                    p.nvic.borrow_mut().return_from_interrupt(&sys);
                    p.nvic.borrow_mut().run_pending_interrupts(&sys, vector_table_addr);
                }
                3 => {
                    error!("intr_hook intno={:08x}", exception);
                }
                _ => {
                    error!("intr_hook intno={:08x}", exception);
                    std::process::exit(1);
                }
            }
        }).expect("add_intr_hook failed");
    }

    uc.add_mem_hook(HookType::MEM_UNMAPPED, 0, u64::MAX, |uc, type_, addr, size, value| {
        if type_ == MemType::WRITE_UNMAPPED {
            warn!("{:?} addr=0x{:08x} size={} value=0x{:08x}", type_, addr, size, value);
        } else {
            warn!("{:?} addr=0x{:08x} size={}", type_, addr, size);
        }

        unsafe {
            let pc = uc.reg_read(RegisterARM::PC).expect("failed to get pc");
            assert!(pc as u32 == LAST_INSTRUCTION.0);
            uc.reg_write(RegisterARM::PC, thumb(pc as u64 + LAST_INSTRUCTION.1 as u64)).unwrap();
        }

        CONTINUE_EXECUTION.store(true, Ordering::Release);

        false
    }).expect("add_mem_hook failed");

    let vector_table = VectorTable::from_memory(&uc, vector_table_addr)?;
    let mut pc = vector_table.reset as u64;
    uc.reg_write(RegisterARM::SP, vector_table.sp.into()).map_err(UniErr)?;
    //uc.reg_write(RegisterARM::LR, 0xFFFF_FFFF).map_err(UniErr)?;

    info!("Starting emulation");

    // Если включен специальный bridge-режим, вместо бесконечного авто-run переходим в command-driven цикл.
    if bridge_mode_enabled() {
        // В bridge-режиме весь контроль над прогрессом исполнения отдается внешнему TUI через stdin-команды.
        return run_bridge_session(&mut uc, pc, framebuffers);
    }

    loop {
        let max_instructions = args.max_instructions.map(|c|
            // yes, we want to panic if this goes negative.
            c - NUM_INSTRUCTIONS.load(Ordering::Relaxed)
        );
        if max_instructions == Some(0) {
            info!("Reached target number of instructions. Done");
            break;
        }

        let result = uc.emu_start(
            pc,
            args.stop_addr.unwrap_or(0) as u64,
            0,
            max_instructions.unwrap_or(0) as usize,
        ).map_err(UniErr);
        pc = uc.reg_read(RegisterARM::PC).expect("failed to get pc");

        if STOP_REQUESTED.load(Ordering::Relaxed) {
            info!("Stop requested");
            break;
        }

        if let Err(e) = result {
            if CONTINUE_EXECUTION.swap(false, Ordering::AcqRel) {
                // This was a bad memory access, we keep going.
                if crate::verbose() >= 3 {
                    trace!("Resuming execution pc={:08x}", pc);
                }
                pc = thumb(pc);
                continue;
            } else {
                bail!(e);
            }
        }

        if args.stop_addr == Some(pc as u32) {
            info!("Stop address reached, stopping");
            break;
        }

        if BUSY_LOOP_REACHED.load(Ordering::Relaxed) {
            break;
        }
    }

    if let Some(n) = args.dump_stack {
        dump_stack(&mut uc, n);
    }

    for fb in framebuffers.images {
        fb.borrow().write_to_disk()?;
    }

    Ok(())
}
