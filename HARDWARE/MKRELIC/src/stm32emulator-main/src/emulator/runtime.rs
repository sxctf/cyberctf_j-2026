/// RU: Read-only снимок, который используют UI и форматирование статуса.
/// EN: Read-only snapshot that the UI and status formatting consume.
///
/// RU: Ментальная модель:
/// RU: - настоящая source of truth живет внутри внешнего процесса эмулятора;
/// RU: - эта структура является стабильной projection-моделью bridge-слоя;
/// RU: - она строится из mutable cache, который постоянно обновляется из логов.
/// EN: Mental model:
/// EN: - the real source of truth lives inside the external emulator process;
/// EN: - this struct is the stable projection exposed by the bridge layer;
/// EN: - it is built from the mutable cache that is continuously updated from logs.
#[allow(dead_code)]
#[derive(Clone, Debug, Default)]
pub(crate) struct BridgeView {
    /// RU: Последний глобальный счетчик инструкций/шагов, полученный от bridge.
    /// EN: Last observed global instruction/step counter emitted by the bridge.
    pub(crate) step: u64,
    /// RU: Снимок core-регистров из последнего `BRIDGE_STATUS`.
    /// EN: Core register snapshot from the most recent `BRIDGE_STATUS`.
    pub(crate) pc: u32,
    pub(crate) sp: u32,
    pub(crate) lr: u32,
    pub(crate) xpsr: u32,
    pub(crate) msp: u32,
    pub(crate) psp: u32,
    /// RU: Пример состояния периферии, которое приходит в status-пакетах.
    /// EN: Example peripheral state tracked in status packets.
    pub(crate) tim2_cnt: u32,
    pub(crate) gpioa_idr: u16,
    pub(crate) gpioa_odr: u16,
    /// RU: Параметры последнего запрошенного memory watch/dump.
    /// EN: Parameters of the last requested memory watch/dump.
    pub(crate) watch_addr: u32,
    pub(crate) watch_len: usize,
    /// RU: Человекочитаемый hexdump, собранный из последнего `BRIDGE_DUMP`.
    /// EN: Human-readable hexdump built from the latest `BRIDGE_DUMP`.
    pub(crate) watch_dump: String,
    /// RU: Compact hex bytes из последнего `BRIDGE_DUMP`; нужен для copy-friendly chunks.
    /// EN: Compact hex bytes from the latest `BRIDGE_DUMP`; used for copy-friendly chunks.
    pub(crate) watch_data_hex: String,
    /// RU: Последний UART payload, замеченный в текстовом output stream.
    /// EN: Last UART payload seen in the textual output stream.
    pub(crate) last_uart_tx: Option<String>,
    /// RU: Pretty-printed дамп регистров, собранный из последнего `BRIDGE_REGS`.
    /// EN: Pretty-printed register dump built from the latest `BRIDGE_REGS`.
    pub(crate) regs_dump: String,
}

/// RU: Mutable cache, восстановленный из логов bridge-протокола.
/// EN: Mutable cache reconstructed from bridge protocol logs.
///
/// RU: В отличие от `BridgeView`, это внутренняя "сантехника": `bridge.rs` меняет
/// RU: cache при replay log markers, а потом строит из него read-only `BridgeView`.
/// EN: Unlike `BridgeView`, this type is internal plumbing: `bridge.rs` mutates it
/// EN: while replaying log markers, and then derives a read-only `BridgeView`.
///
/// RU: Ментальная модель:
/// RU: - эта структура только локальный snapshot, собранный из `BRIDGE_*` строк;
/// RU: - поля обновляются opportunistically при replay свежих логов в `bridge.rs`.
/// EN: Mental model:
/// EN: - this struct is only a local snapshot assembled from `BRIDGE_*` lines;
/// EN: - fields are updated opportunistically when `bridge.rs` replays recent logs.
#[derive(Clone, Debug, Default)]
pub(crate) struct BridgeRuntimeCache {
    /// RU: Последний глобальный счетчик инструкций/шагов, полученный от bridge.
    /// EN: Last observed global instruction/step counter emitted by the bridge.
    pub(crate) step: u64,
    /// RU: Снимок core-регистров из последнего `BRIDGE_STATUS`.
    /// EN: Core register snapshot from the most recent `BRIDGE_STATUS`.
    pub(crate) pc: u32,
    pub(crate) sp: u32,
    pub(crate) lr: u32,
    pub(crate) xpsr: u32,
    pub(crate) msp: u32,
    pub(crate) psp: u32,
    /// RU: Пример состояния периферии, которое приходит в status-пакетах.
    /// EN: Example peripheral state tracked in status packets.
    pub(crate) tim2_cnt: u32,
    pub(crate) gpioa_idr: u16,
    pub(crate) gpioa_odr: u16,
    /// RU: Параметры последнего запрошенного memory watch/dump.
    /// EN: Parameters of the last requested memory watch/dump.
    pub(crate) watch_addr: u32,
    pub(crate) watch_len: usize,
    /// RU: Человекочитаемый hexdump, собранный из последнего `BRIDGE_DUMP`.
    /// EN: Human-readable hexdump built from the latest `BRIDGE_DUMP`.
    pub(crate) watch_dump: String,
    /// RU: Compact hex bytes из последнего `BRIDGE_DUMP`; нужен для copy-friendly chunks.
    /// EN: Compact hex bytes from the latest `BRIDGE_DUMP`; used for copy-friendly chunks.
    pub(crate) watch_data_hex: String,
    /// RU: Последний UART payload, замеченный в текстовом output stream.
    /// EN: Last UART payload seen in the textual output stream.
    pub(crate) last_uart_tx: Option<String>,
    /// RU: Pretty-printed дамп регистров, собранный из последнего `BRIDGE_REGS`.
    /// EN: Pretty-printed register dump built from the latest `BRIDGE_REGS`.
    pub(crate) regs_dump: String,
}

impl From<&BridgeRuntimeCache> for BridgeView {
    /// RU: Копирует mutable parser cache в immutable read model.
    /// EN: Copies the mutable parser cache into an immutable read model.
    ///
    /// RU: Точки clone здесь намеренные: после конвертации presentation-код владеет
    /// RU: стабильным snapshot и не видит мутаций парсера посреди render.
    /// EN: The clone points are deliberate: after this conversion, presentation code
    /// EN: owns a stable snapshot and cannot observe later log parsing mutations mid-render.
    fn from(cache: &BridgeRuntimeCache) -> Self {
        Self {
            step: cache.step,
            pc: cache.pc,
            sp: cache.sp,
            lr: cache.lr,
            xpsr: cache.xpsr,
            msp: cache.msp,
            psp: cache.psp,
            tim2_cnt: cache.tim2_cnt,
            gpioa_idr: cache.gpioa_idr,
            gpioa_odr: cache.gpioa_odr,
            watch_addr: cache.watch_addr,
            watch_len: cache.watch_len,
            watch_dump: cache.watch_dump.clone(),
            watch_data_hex: cache.watch_data_hex.clone(),
            last_uart_tx: cache.last_uart_tx.clone(),
            regs_dump: cache.regs_dump.clone(),
        }
    }
}
