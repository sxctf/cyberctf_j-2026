use std::{
    collections::VecDeque,
    io::{BufRead, BufReader, Write},
    process::{Child, ChildStdin, Command, Stdio},
    sync::{Arc, Mutex},
    thread,
    time::{Duration, Instant},
};

use anyhow::{Result, anyhow};

use crate::challenge::challenges::ChallengeKind;

use super::{
    boards::{BoardView, challenge_slug},
    launch::BridgeLaunch,
    runtime::{BridgeRuntimeCache, BridgeView},
    util::{
        BRIDGE_LOG_LIMIT, DEFAULT_TIMEOUT_MS, decode_hex_bytes, format_addr, format_hexdump,
        parse_u32_token, set_u32,
    },
};

pub type EmulatorRuntime = Stm32EmulatorBridge;

#[derive(Clone, Debug)]
enum BridgeState {
    /// RU: Процесс еще не запускался или был намеренно остановлен перед reconnect.
    /// EN: Process was not started yet or was intentionally stopped before reconnect.
    Idle,
    /// RU: Child process жив, stdin/stdout pipes подключены.
    /// EN: Child process is alive and stdin/stdout pipes are attached.
    Connected,
    /// RU: Ошибка запуска или runtime-взаимодействия; детали смотри в logs/status.
    /// EN: Process launch or runtime interaction failed; inspect logs/status for detail.
    Error,
}

/// RU: Адаптер между TUI и внешним процессом STM32-эмулятора.
/// EN: Adapter between the TUI and an external STM32 emulator process.
///
/// RU: Ментальная модель:
/// RU: - этот тип владеет child process и подключенными к нему pipes;
/// RU: - background reader threads складывают stdout/stderr child в `shared_log`;
/// RU: - действия пользователя превращаются в строки, записанные в child stdin;
/// RU: - `runtime_cache` не authoritative state, а cache из log markers;
/// RU: - `BridgeView` — стабильная read-only projection из этого cache;
/// RU: - `BoardView` — более богатый UI snapshot: bridge state плюс сигналы задания.
/// EN: Mental model:
/// EN: - this type owns the child process and the pipes connected to it;
/// EN: - background reader threads push child stdout/stderr into `shared_log`;
/// EN: - user actions are translated into lines written to child stdin;
/// EN: - `runtime_cache` is not authoritative state, but a cache rebuilt from log markers;
/// EN: - `BridgeView` is the stable read-only projection derived from that cache;
/// EN: - `BoardView` is a richer UI snapshot: bridge state plus challenge-specific signals.
pub struct Stm32EmulatorBridge {
    challenge: ChallengeKind,
    state: BridgeState,
    child_stdin: Option<ChildStdin>,
    child_process: Option<Child>,
    shared_log: Arc<Mutex<VecDeque<String>>>,
    command_log: Vec<String>,
    status_line: String,
    last_sent: Option<String>,
    launch: BridgeLaunch,
    runtime_cache: BridgeRuntimeCache,
}

impl Stm32EmulatorBridge {
    /// RU: Создает bridge в disconnected state.
    /// EN: Creates the bridge in a disconnected state.
    ///
    /// RU: Здесь процесс не запускается. `connect()` отвечает за launch и pipe setup.
    /// EN: No process is spawned here. `connect()` performs launch and pipe setup.
    pub fn new(challenge: ChallengeKind) -> Self {
        Self {
            challenge,
            state: BridgeState::Idle,
            child_stdin: None,
            child_process: None,
            shared_log: Arc::new(Mutex::new(VecDeque::with_capacity(BRIDGE_LOG_LIMIT))),
            command_log: Vec::new(),
            status_line: "Bridge created, waiting for connect()".to_string(),
            last_sent: None,
            launch: BridgeLaunch::resolve(),
            runtime_cache: BridgeRuntimeCache::default(),
        }
    }

    /// RU: Запускает настроенный процесс эмулятора и подключает log readers.
    /// EN: Starts the configured emulator process and attaches log readers.
    ///
    /// RU: В bridge protocol mode функция также ждет `BRIDGE_READY`, поэтому
    /// RU: следующие status reads могут считать, что protocol bootstrap завершен.
    /// EN: In bridge protocol mode this also waits for `BRIDGE_READY`, so subsequent
    /// EN: status reads can assume the child has finished its protocol bootstrap.
    pub fn connect(&mut self) -> Result<()> {
        self.refresh_process_state();
        if matches!(self.state, BridgeState::Connected) {
            return Ok(());
        }

        self.launch
            .validate()
            .map_err(|error| self.record_error(error.to_string()))?;

        let mut process = Command::new(&self.launch.command);
        process
            .args(&self.launch.args)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());

        if let Some(workdir) = &self.launch.workdir {
            process.current_dir(workdir);
        }

        if self.launch.bridge_protocol {
            process.env("STM32_EMULATOR_BRIDGE_MODE", "1");
            process.env("CMAKE_POLICY_VERSION_MINIMUM", "3.5");
        }

        match process.spawn() {
            Ok(mut child) => {
                self.child_stdin = child.stdin.take();
                self.attach_output_readers(&mut child);
                self.child_process = Some(child);
                self.state = BridgeState::Connected;
                self.status_line = format!(
                    "Connected to `{}` with {} arg(s): {}",
                    self.launch.command,
                    self.launch.args.len(),
                    self.launch.description
                );
                self.push_bridge_log(format!("bridge: spawned `{}`", self.launch.command));

                if self.launch.bridge_protocol {
                    if self.wait_for_marker("BRIDGE_READY", 20_000) {
                        self.sync_runtime_from_logs();
                    } else {
                        self.status_line =
                            "Spawned process, but BRIDGE_READY was not observed before timeout"
                                .to_string();
                    }
                }

                Ok(())
            }
            Err(error) => Err(self.record_error(format!(
                "failed to spawn `{}`: {}",
                self.launch.command, error
            ))),
        }
    }

    /// RU: Строит read-only snapshot сырого состояния эмулятора из bridge logs.
    /// EN: Builds a read-only snapshot of raw emulator state parsed from bridge logs.
    ///
    /// RU: Он намеренно меньше, чем `BoardView`: отвечает на вопрос "что эмулятор
    /// RU: сообщил последним?" и не знает про TUI labels, command history или
    /// RU: challenge-specific flags вроде `service_mode`.
    /// EN: This is intentionally smaller than `BoardView`: it answers "what did the
    /// EN: emulator last report?" and does not know about TUI labels, command history,
    /// EN: or challenge-specific booleans such as `service_mode`.
    fn runtime_view(&self) -> BridgeView {
        BridgeView::from(&self.runtime_cache)
    }

    /// RU: Формирует human-readable summary bridge и cached emulator state.
    /// EN: Renders a human-readable summary of the bridge and cached emulator state.
    ///
    /// RU: Эта строка показывается в status panel TUI.
    /// EN: This is the string shown in the TUI status panel.
    pub fn status_text(&self) -> String {
        let view = self.runtime_view();
        format!(
            "bridge_state={:?}\nchallenge={}\nstep={}\npc={}\nsp={}\nlr={}\nxpsr={}\nmsp={}\npsp={}\ntim2_cnt={}\ngpioa_idr={:#06x}\ngpioa_odr={:#06x}\nlast_sent={:?}\nlast_uart_tx={:?}\nstatus={}",
            self.state,
            challenge_slug(self.challenge),
            view.step,
            format_addr(view.pc),
            format_addr(view.sp),
            format_addr(view.lr),
            format_addr(view.xpsr),
            format_addr(view.msp),
            format_addr(view.psp),
            format_addr(view.tim2_cnt),
            view.gpioa_idr,
            view.gpioa_odr,
            self.last_sent,
            view.last_uart_tx,
            self.status_line
        )
    }

    /// RU: Строит snapshot платы, который потребляет TUI.
    /// EN: Builds the board snapshot consumed by the TUI.
    ///
    /// RU: Snapshot означает "стабильная копия на один render frame". TUI получает
    /// RU: это значение вместо borrow `Stm32EmulatorBridge`, поэтому render не может
    /// RU: мутировать child process, блокироваться на IO или видеть half-updated fields.
    /// EN: Snapshot means "a stable copy for one render frame". The TUI receives this
    /// EN: value instead of borrowing `Stm32EmulatorBridge`, so rendering cannot mutate
    /// EN: the child process, block on IO, or observe half-updated fields while drawing.
    pub fn view(&self) -> BoardView {
        let view = self.runtime_view();
        let emulator_log = self.logs();
        let uart_log = emulator_log
            .iter()
            .filter(|line| line.contains("UART"))
            .cloned()
            .collect::<Vec<_>>();
        let gpioa_state = view.gpioa_odr | view.gpioa_idr;
        let service_mode = (gpioa_state & 0x0001) != 0;
        let pa0_high = (gpioa_state & 0x0001) != 0;
        let pa5_led_on = (view.gpioa_odr & (1 << 5)) != 0;

        BoardView {
            challenge: self.challenge,
            title: match self.challenge {
                ChallengeKind::SramRecovery => "SRAM Recovery".to_string(),
                ChallengeKind::GlitchUnlock => "Glitch Unlock".to_string(),
            },
            brief: match self.challenge {
                ChallengeKind::SramRecovery => {
                    "Observe bridge state, inspect memory, and recover SRAM-backed data."
                        .to_string()
                }
                ChallengeKind::GlitchUnlock => {
                    "Step the emulator, toggle pins, and inspect the unlock timing window."
                        .to_string()
                }
            },
            step: view.step,
            tim2_cnt: view.tim2_cnt,
            gpioa_idr: view.gpioa_idr,
            gpioa_odr: view.gpioa_odr,
            service_mode,
            pa0_high,
            pa5_led_on,
            watch_addr: view.watch_addr,
            watch_len: view.watch_len,
            armed_ticks_left: 0,
            fault_window_open: false,
            manifest_present: !view.watch_dump.is_empty(),
            service_latch: 0,
            flag_window_locked: false,
            flash_flag_blob_present: false,
            last_uart_rx: self.last_sent.clone(),
            last_uart_tx: view.last_uart_tx,
            status_line: self.status_line.clone(),
            uart_log,
            emulator_log,
            watch_dump: view.watch_dump,
            command_log: self.command_log.clone(),
        }
    }

    /// RU: Возвращает presentation log после фильтрации известного low-value шума.
    /// EN: Returns the presentation log after filtering known noisy low-value lines.
    pub fn logs(&self) -> Vec<String> {
        self.presentation_log()
    }

    /// RU: Возвращает команды, ранее отправленные в bridge, для debug control flow.
    /// EN: Returns commands previously sent to the bridge for debugging the control flow.
    pub fn command_log(&self) -> &[String] {
        &self.command_log
    }

    /// RU: Показывает, умеет ли текущий launch target явный `:bridge` protocol.
    /// EN: Whether the current launch target speaks the explicit `:bridge` protocol.
    pub fn bridge_protocol(&self) -> bool {
        self.launch.bridge_protocol
    }

    /// RU: Обновляет cached status и возвращает formatted snapshot.
    /// EN: Refreshes the cached status and returns the formatted snapshot.
    ///
    /// RU: В protocol mode функция активно просит child выполнить `status`.
    /// RU: Без protocol она может только перепарсить уже существующий text output.
    /// EN: In protocol mode this actively asks the child for `status`.
    /// EN: Without the protocol it can only rescan whatever text output already exists.
    pub fn request_status(&mut self) -> String {
        if self.launch.bridge_protocol {
            let _ = self.send_control("status");
            return self.wait_for(DEFAULT_TIMEOUT_MS);
        }
        self.refresh_process_state();
        self.sync_runtime_from_logs();
        self.status_text()
    }

    /// RU: Выполняет одну текстовую команду управления runtime.
    /// EN: Executes one textual runtime control command.
    ///
    /// RU: Это общий command router для UI-слоев: публичный API называется
    /// RU: `exec_command`, и callers должны использовать именно его.
    /// EN: This is the shared command router for UI layers: the public API is named
    /// EN: `exec_command`, and callers should use that exact method.
    pub fn exec_command(&mut self, line: &str) -> String {
        let input = line.trim();
        if input.is_empty() {
            return String::new();
        }
        if input == "status" {
            return self.request_status();
        }
        if input == "help" {
            return [
                "commands:",
                "  status",
                "  help",
                "  uart <text>",
                "  step <n>",
                "  dump <addr> <len>",
                "  dumpchunk <addr> <len>",
                "  watch <addr> <len>",
                "  regs",
                "  pin set <pin> <0|1>",
                "  reset",
                "  esc",
            ]
            .join("\n");
        }
        if input == "reset" {
            return match self.restart() {
                Ok(()) => "runtime restarted".to_string(),
                Err(error) => format!("runtime restart failed: {error}"),
            };
        }
        if let Some(rest) = input.strip_prefix("step ") {
            return match rest.trim().parse::<u64>() {
                Ok(steps) => self.step(steps),
                Err(_) => "step expects an integer counter".to_string(),
            };
        }
        if let Some(rest) = input.strip_prefix("uart ") {
            return self.send_uart(rest);
        }
        if input == "regs" {
            return self.regs_dump().unwrap_or_else(|| {
                "regs is only implemented for the bridge protocol runtime".to_string()
            });
        }
        if let Some(rest) = input.strip_prefix("dump ") {
            return match parse_addr_len(rest) {
                Some((addr, len)) => self.dump_memory(addr, len).unwrap_or_else(|| {
                    "dump is only implemented for the bridge protocol runtime".to_string()
                }),
                None => "dump expects address and length".to_string(),
            };
        }
        if let Some(rest) = input.strip_prefix("dumpchunk ") {
            return match parse_addr_len(rest) {
                Some((addr, len)) => self.dump_memory_compact(addr, len).unwrap_or_else(|| {
                    "dumpchunk is only implemented for the bridge protocol runtime".to_string()
                }),
                None => "dumpchunk expects address and length".to_string(),
            };
        }
        if input == "dumpchunk" {
            return "dumpchunk expects address and length, example: dumpchunk 0x20000000 32"
                .to_string();
        }
        if let Some(rest) = input.strip_prefix("watch ") {
            return self.exec_command(&format!("dump {rest}"));
        }
        if let Some(rest) = input.strip_prefix("pin set ") {
            let mut parts = rest.split_whitespace();
            let Some(pin_name) = parts.next() else {
                return "pin set expects a pin name and level".to_string();
            };
            let Some(level) = parts.next() else {
                return "pin set expects a pin name and level".to_string();
            };
            return self.set_pin_level(pin_name, level).unwrap_or_else(|| {
                "pin set is only implemented for the bridge protocol runtime".to_string()
            });
        }
        if input.starts_with("pin ") {
            return "only `pin set <pin> <0|1>` is implemented".to_string();
        }
        format!("unknown command: {input}")
    }

    /// RU: Перезапускает внешний процесс и сбрасывает cached runtime snapshot.
    /// EN: Restarts the external process and drops any cached runtime snapshot.
    pub fn restart(&mut self) -> Result<()> {
        self.stop_process();
        self.state = BridgeState::Idle;
        self.status_line = "Bridge restarting external process".to_string();
        self.runtime_cache = BridgeRuntimeCache::default();
        self.connect()
    }

    /// RU: Продвигает выполнение и возвращает обновленный status text.
    /// EN: Advances execution and returns the refreshed status text.
    ///
    /// RU: В protocol mode stepping явный. В plain-text mode мы можем только ждать
    /// RU: новый output, поэтому delay — approximation, а не реальная команда.
    /// EN: In protocol mode stepping is explicit. In plain-text mode we can only wait
    /// EN: for more output, so the delay is an approximation rather than a real command.
    pub fn step(&mut self, steps: u64) -> String {
        if self.launch.bridge_protocol {
            let _ = self.send_control(&format!("step {steps}"));
            return self.wait_for(DEFAULT_TIMEOUT_MS);
        }
        self.wait_for(steps.saturating_mul(75))
    }

    /// RU: Отправляет UART input в child process.
    /// EN: Sends UART input to the child process.
    ///
    /// RU: Protocol mode оборачивает текст в control command `:bridge uart ...`.
    /// RU: Fallback mode пишет текст напрямую в stdin.
    /// EN: Protocol mode wraps the text in a `:bridge uart ...` control command.
    /// EN: Fallback mode writes the text directly to stdin.
    pub fn send_uart(&mut self, text: &str) -> String {
        if self.launch.bridge_protocol {
            let _ = self.send_control(&format!("uart {text}"));
            return self.wait_for(25);
        }
        self.send_line(text)
    }

    /// RU: Запрашивает formatted register dump через bridge protocol.
    /// EN: Requests a formatted register dump from the bridge protocol.
    ///
    /// RU: Возвращает `None`, если child не реализует bridge protocol.
    /// EN: Returns `None` when the child does not implement the bridge protocol.
    pub fn regs_dump(&mut self) -> Option<String> {
        if !self.launch.bridge_protocol {
            return None;
        }
        let _ = self.send_control("regs");
        let _ = self.wait_for(DEFAULT_TIMEOUT_MS);
        (!self.runtime_cache.regs_dump.is_empty()).then(|| self.runtime_cache.regs_dump.clone())
    }

    /// RU: Запрашивает memory dump и возвращает последний parsed hexdump snapshot.
    /// EN: Requests a memory dump and returns the last parsed hexdump snapshot.
    ///
    /// RU: `watch_addr` и `watch_len` обновляются еще до ответа, чтобы bridge знал,
    /// RU: какой областью памяти сейчас интересуется UI.
    /// EN: `watch_addr` and `watch_len` are updated even before the response arrives
    /// EN: so the bridge tracks what region the UI is currently interested in.
    pub fn dump_memory(&mut self, addr: u32, len: usize) -> Option<String> {
        self.runtime_cache.watch_addr = addr;
        self.runtime_cache.watch_len = len;
        if !self.launch.bridge_protocol {
            return None;
        }
        let _ = self.send_control(&format!("dump {} {}", format_addr(addr), len));
        let _ = self.wait_for(DEFAULT_TIMEOUT_MS);
        (!self.runtime_cache.watch_dump.is_empty()).then(|| self.runtime_cache.watch_dump.clone())
    }

    /// RU: Запрашивает memory dump и возвращает copy-friendly compact hex chunk.
    /// EN: Requests memory dump and returns a copy-friendly compact hex chunk.
    pub fn dump_memory_compact(&mut self, addr: u32, len: usize) -> Option<String> {
        self.runtime_cache.watch_addr = addr;
        self.runtime_cache.watch_len = len;
        self.runtime_cache.watch_data_hex.clear();
        if !self.launch.bridge_protocol {
            return None;
        }
        let _ = self.send_control(&format!("dump {} {}", format_addr(addr), len));
        let _ = self.wait_for(DEFAULT_TIMEOUT_MS);
        (!self.runtime_cache.watch_data_hex.is_empty()).then(|| {
            format!(
                "chunk addr={} len={} data={}",
                format_addr(addr),
                len,
                self.runtime_cache.watch_data_hex
            )
        })
    }

    /// RU: Отправляет команду изменения pin и затем запрашивает свежий status snapshot.
    /// EN: Sends a pin mutation command and then requests a fresh status snapshot.
    pub fn set_pin_level(&mut self, pin_name: &str, level: &str) -> Option<String> {
        if !self.launch.bridge_protocol {
            return None;
        }
        let _ = self.send_control(&format!("pin set {pin_name} {level}"));
        let _ = self.send_control("status");
        Some(self.wait_for(DEFAULT_TIMEOUT_MS))
    }

    /// RU: Передает ownership stdout/stderr child в reader threads, которые наполняют `shared_log`.
    /// EN: Moves child stdout/stderr ownership into reader threads that feed `shared_log`.
    fn attach_output_readers(&self, child: &mut Child) {
        if let Some(stdout) = child.stdout.take() {
            spawn_reader_thread(Arc::clone(&self.shared_log), stdout, "stdout");
        }
        if let Some(stderr) = child.stderr.take() {
            spawn_reader_thread(Arc::clone(&self.shared_log), stderr, "stderr");
        }
    }

    /// RU: Оборачивает команду в текстовый prefix bridge protocol.
    /// EN: Wraps a command in the textual bridge protocol prefix.
    fn send_control(&mut self, command: &str) -> String {
        self.send_line(&format!(":bridge {command}"))
    }

    /// RU: Пишет одну raw line в child stdin и записывает intent в `command_log`.
    /// EN: Writes one raw line to child stdin and records the intent in `command_log`.
    ///
    /// RU: Функция не ждет ответ child; high-level методы сами решают, нужно ли
    /// RU: sleep и rescan logs после отправки команды.
    /// EN: This function does not wait for the child response; higher-level methods
    /// EN: decide whether they need to sleep and rescan logs after sending the command.
    fn send_line(&mut self, line: &str) -> String {
        self.refresh_process_state();
        let Some(stdin) = self.child_stdin.as_mut() else {
            return "bridge stdin is not available".to_string();
        };

        let write_result = writeln!(stdin, "{line}");
        let flush_result = stdin.flush();

        if write_result.is_ok() && flush_result.is_ok() {
            self.last_sent = Some(line.to_string());
            self.status_line = format!("Forwarded to child stdin: `{line}`");
            self.command_log.push(format!("> {line}"));
            return format!("bridge forwarded `{line}`");
        }

        self.status_line = format!("Failed to write to child stdin: `{line}`");
        self.command_log.push(format!("! failed: {line}"));
        format!("bridge write failed for `{line}`")
    }

    /// RU: Дает child время отреагировать, затем пересобирает local snapshot из logs.
    /// EN: Gives the child time to react, then rebuilds the local snapshot from logs.
    ///
    /// RU: Delay намеренно coarse-grained: bridge poll-ит text output, а не работает
    /// RU: через acknowledgements или structured request-response channel.
    /// EN: The delay is intentionally coarse-grained: this bridge is polling text
    /// EN: output, not coordinating via acknowledgements or a structured channel.
    fn wait_for(&mut self, wait_ms: u64) -> String {
        thread::sleep(Duration::from_millis(wait_ms.min(30_000)));
        self.refresh_process_state();
        self.sync_runtime_from_logs();
        self.status_text()
    }

    /// RU: Replay-ит текущий presentation log и обновляет `runtime` из bridge markers.
    /// EN: Replays the current presentation log and updates `runtime` from bridge markers.
    ///
    /// RU: Один и тот же log можно парсить много раз; updates idempotent, потому что
    /// RU: каждый marker перезаписывает cache последними значениями из stream.
    /// EN: The same log can be parsed multiple times; updates are idempotent because
    /// EN: every marker overwrites cached fields with the latest values in the stream.
    fn sync_runtime_from_logs(&mut self) {
        for line in self.presentation_log() {
            if let Some((_, payload)) = line.split_once("BRIDGE_STATUS ") {
                self.apply_status_line(payload);
            }
            if let Some((_, payload)) = line.split_once("BRIDGE_DUMP ") {
                self.apply_dump_line(payload);
            }
            if let Some((_, payload)) = line.split_once("BRIDGE_REGS ") {
                self.apply_regs_line(payload);
            }
            if let Some((_, payload)) = line.split_once("UART_TX:") {
                self.runtime_cache.last_uart_tx = Some(payload.to_string());
            }
        }
    }

    /// RU: Возвращает logs для UI, скрывая несколько повторяющихся noisy events.
    /// EN: Returns logs intended for UI consumption, hiding recurring noisy events.
    fn presentation_log(&self) -> Vec<String> {
        self.snapshot_log()
            .into_iter()
            .filter(|line| {
                !line.contains("READ_UNMAPPED addr=0x0000001d")
                    && !line.contains("WRITE_UNMAPPED addr=0x00000010")
                    && !line.contains("WRITE_UNMAPPED addr=0x00000014")
            })
            .collect()
    }

    /// RU: Делает point-in-time копию shared log buffer.
    /// EN: Takes a point-in-time copy of the shared log buffer.
    ///
    /// RU: Копирование не держит mutex во время downstream parsing/filtering.
    /// EN: Copying avoids holding the mutex while downstream parsing/filtering runs.
    fn snapshot_log(&self) -> Vec<String> {
        self.shared_log
            .lock()
            .map(|guard| guard.iter().cloned().collect())
            .unwrap_or_else(|_| vec!["bridge-error: failed to lock shared log".to_string()])
    }

    /// RU: Poll-ит shared log, пока не появится marker или не истечет timeout.
    /// EN: Polls the shared log until a specific marker appears or the timeout expires.
    ///
    /// RU: На startup отличает "process spawned" от "bridge protocol ready".
    /// EN: Used during startup to distinguish "process spawned" from "bridge ready".
    fn wait_for_marker(&self, marker: &str, timeout_ms: u64) -> bool {
        let start_len = self.snapshot_log().len();
        let start = Instant::now();

        while start.elapsed().as_millis() < timeout_ms as u128 {
            let lines = self.snapshot_log();
            if lines
                .iter()
                .skip(start_len.min(lines.len()))
                .any(|line| line.contains(marker))
            {
                return true;
            }
            thread::sleep(Duration::from_millis(25));
        }

        false
    }

    /// RU: Синхронизирует `state` с реальным lifecycle child process.
    /// EN: Synchronizes `state` with the real child process lifecycle.
    ///
    /// RU: Это guardrail: silently exited child превращается в видимый bridge state.
    /// EN: This guardrail turns a silently exited child into visible bridge state.
    fn refresh_process_state(&mut self) {
        let Some(child) = self.child_process.as_mut() else {
            return;
        };

        match child.try_wait() {
            Ok(None) => {}
            Ok(Some(status)) => {
                let exit_text = status
                    .code()
                    .map(|code| format!("exit code {code}"))
                    .unwrap_or_else(|| "signal termination".to_string());
                self.state = BridgeState::Error;
                self.child_stdin = None;
                self.child_process = None;
                self.status_line = format!(
                    "external process `{}` exited with {}",
                    self.launch.command, exit_text
                );
                self.push_bridge_log(format!("bridge-error: {}", self.status_line));
            }
            Err(error) => {
                let _: anyhow::Error =
                    self.record_error(format!("failed to poll child process state: {error}"));
            }
        }
    }

    /// RU: Парсит один `BRIDGE_STATUS` payload в cached runtime snapshot.
    /// EN: Parses one `BRIDGE_STATUS` payload into the cached runtime snapshot.
    fn apply_status_line(&mut self, payload: &str) {
        for token in payload.split_whitespace() {
            let Some((key, value)) = token.split_once('=') else {
                continue;
            };
            match key {
                "step" => {
                    if let Ok(parsed) = value.parse::<u64>() {
                        self.runtime_cache.step = parsed;
                    }
                }
                "pc" => set_u32(value, &mut self.runtime_cache.pc),
                "sp" => set_u32(value, &mut self.runtime_cache.sp),
                "lr" => set_u32(value, &mut self.runtime_cache.lr),
                "xpsr" => set_u32(value, &mut self.runtime_cache.xpsr),
                "msp" => set_u32(value, &mut self.runtime_cache.msp),
                "psp" => set_u32(value, &mut self.runtime_cache.psp),
                "tim2_cnt" => set_u32(value, &mut self.runtime_cache.tim2_cnt),
                "gpioa_idr" => {
                    if let Some(parsed) = parse_u32_token(value) {
                        self.runtime_cache.gpioa_idr = parsed as u16;
                    }
                }
                "gpioa_odr" => {
                    if let Some(parsed) = parse_u32_token(value) {
                        self.runtime_cache.gpioa_odr = parsed as u16;
                    }
                }
                _ => {}
            }
        }

        self.status_line = format!(
            "pc={} sp={} step={} tim2_cnt={}",
            format_addr(self.runtime_cache.pc),
            format_addr(self.runtime_cache.sp),
            self.runtime_cache.step,
            format_addr(self.runtime_cache.tim2_cnt)
        );
    }

    /// RU: Парсит один `BRIDGE_DUMP` payload и пересобирает printable hexdump cache.
    /// EN: Parses one `BRIDGE_DUMP` payload and rebuilds the printable hexdump cache.
    fn apply_dump_line(&mut self, payload: &str) {
        let mut addr = None;
        let mut len = None;
        let mut data_hex = None;

        for token in payload.split_whitespace() {
            let Some((key, value)) = token.split_once('=') else {
                continue;
            };
            match key {
                "addr" => addr = parse_u32_token(value),
                "len" => len = value.parse::<usize>().ok(),
                "data" => data_hex = Some(value),
                _ => {}
            }
        }

        let (Some(addr), Some(len), Some(data_hex)) = (addr, len, data_hex) else {
            return;
        };

        self.runtime_cache.watch_addr = addr;
        self.runtime_cache.watch_len = len;
        self.runtime_cache.watch_data_hex = data_hex.to_string();
        self.runtime_cache.watch_dump = format_hexdump(addr, &decode_hex_bytes(data_hex));
    }

    /// RU: Парсит один `BRIDGE_REGS` payload в стабильный human-readable список регистров.
    /// EN: Parses one `BRIDGE_REGS` payload into a stable human-readable register listing.
    fn apply_regs_line(&mut self, payload: &str) {
        self.runtime_cache.regs_dump = payload
            .split_whitespace()
            .filter_map(|token| token.split_once('='))
            .filter_map(|(key, value)| parse_u32_token(value).map(|parsed| (key, parsed)))
            .map(|(key, parsed)| format!("{key:>4} = {}", format_addr(parsed)))
            .collect::<Vec<_>>()
            .join("\n");
    }

    /// RU: Добавляет строку в bounded shared log ring buffer.
    /// EN: Appends a line to the bounded shared log ring buffer.
    fn push_bridge_log(&self, line: String) {
        if let Ok(mut guard) = self.shared_log.lock() {
            if guard.len() >= BRIDGE_LOG_LIMIT {
                guard.pop_front();
            }
            guard.push_back(line);
        }
    }

    /// RU: Переводит bridge в error state и возвращает соответствующий `anyhow::Error`.
    /// EN: Transitions the bridge into an error state and returns a matching `anyhow::Error`.
    fn record_error(&mut self, message: impl Into<String>) -> anyhow::Error {
        let error = anyhow!(message.into());
        self.state = BridgeState::Error;
        self.status_line = error.to_string();
        self.push_bridge_log(format!("bridge-error: {}", self.status_line));
        error
    }

    /// RU: Завершает child process, если он еще работает, и очищает pipe handles.
    /// EN: Terminates the child process if it is still running and clears pipe handles.
    fn stop_process(&mut self) {
        if let Some(child) = self.child_process.as_mut() {
            let _ = child.kill();
            let _ = child.wait();
        }
        self.child_stdin = None;
        self.child_process = None;
    }
}

impl Drop for Stm32EmulatorBridge {
    /// RU: Чистит внешний процесс эмулятора при drop bridge.
    /// EN: Cleans up the external emulator process when the bridge is dropped.
    ///
    /// RU: Это не дает terminal app оставить detached child process, если caller
    /// RU: выходит через error path вместо явного restart/stop.
    /// EN: This keeps the terminal app from leaving a detached child process behind
    /// EN: if the caller exits through an error path instead of explicit restart/stop.
    fn drop(&mut self) {
        self.stop_process();
    }
}

/// RU: Непрерывно копирует один output stream child в shared ring buffer.
/// EN: Continuously copies one child output stream into the shared ring buffer.
///
/// RU: Каждый reader работает независимо, поэтому stdout и stderr читаются
/// RU: concurrently и не блокируют основной bridge control path.
/// EN: Each reader runs independently so stdout and stderr can be consumed
/// EN: concurrently without blocking the main bridge control path.
fn spawn_reader_thread<R>(
    shared_log: Arc<Mutex<VecDeque<String>>>,
    reader: R,
    stream_name: &'static str,
) where
    R: std::io::Read + Send + 'static,
{
    thread::spawn(move || {
        let reader = BufReader::new(reader);
        for line in reader.lines().map_while(Result::ok) {
            if let Ok(mut guard) = shared_log.lock() {
                if guard.len() >= BRIDGE_LOG_LIMIT {
                    guard.pop_front();
                }
                guard.push_back(format!("{stream_name}: {line}"));
            }
        }
    });
}

/// RU: Парсит пары `<addr> <len>` для runtime command router.
/// EN: Parses `<addr> <len>` pairs for the runtime command router.
fn parse_addr_len(input: &str) -> Option<(u32, usize)> {
    let mut parts = input.split_whitespace();
    let addr = parts.next().and_then(parse_u32_token)?;
    let len = parts.next()?.parse::<usize>().ok()?;
    Some((addr, len))
}
