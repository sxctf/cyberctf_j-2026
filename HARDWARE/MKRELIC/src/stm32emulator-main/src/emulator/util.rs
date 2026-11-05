pub const BRIDGE_LOG_LIMIT: usize = 256;
pub const DEFAULT_TIMEOUT_MS: u64 = 50;

/// RU: Разбивает строку аргументов из environment на process arguments.
/// EN: Splits an environment-provided argument string into process arguments.
///
/// RU: Это намеренно простой shell-free parser: env overrides нужны для простых
/// RU: локальных запусков, а отказ от shell parsing убирает неожиданные эффекты.
/// EN: This is intentionally small and shell-free: environment overrides are for
/// EN: simple local launches, and avoiding shell parsing prevents surprising behavior.
pub fn split_args(input: &str) -> Vec<String> {
    input.split_whitespace().map(ToString::to_string).collect()
}

/// RU: Парсит `u32` token в decimal или `0x` hexadecimal формате.
/// EN: Parses a `u32` token in decimal or `0x` hexadecimal form.
///
/// RU: Bridge status lines смешивают hex-адреса и decimal-счетчики, поэтому все
/// RU: protocol parsers используют общий helper вместо дублирования.
/// EN: Bridge status lines mix human-friendly hex addresses with decimal counters,
/// EN: so all protocol parsers share this helper instead of duplicating parsing.
pub fn parse_u32_token(value: &str) -> Option<u32> {
    if let Some(hex) = value
        .strip_prefix("0x")
        .or_else(|| value.strip_prefix("0X"))
    {
        u32::from_str_radix(hex, 16).ok()
    } else {
        value.parse::<u32>().ok()
    }
}

/// RU: Обновляет target field только если parsing успешен.
/// EN: Updates a target field only when parsing succeeds.
///
/// RU: Частичные или шумные bridge lines не должны стирать последнее хорошее
/// RU: snapshot-значение; helper кодирует policy "keep old value on bad token".
/// EN: Partial or noisy bridge lines should not erase the last good snapshot value;
/// EN: this helper encodes the "keep old value on bad token" policy.
pub fn set_u32(value: &str, target: &mut u32) {
    if let Some(parsed) = parse_u32_token(value) {
        *target = parsed;
    }
}

/// RU: Конвертирует ASCII hex string в raw bytes.
/// EN: Converts an ASCII hex string into raw bytes.
///
/// RU: `BRIDGE_DUMP` отдает память compact hex-строкой. Невалидный хвост или
/// RU: malformed pairs игнорируются, чтобы одна плохая пара байт не уронила TUI.
/// EN: `BRIDGE_DUMP` emits memory as compact hex. Invalid trailing or malformed
/// EN: pairs are ignored so one bad byte pair does not panic the TUI.
pub fn decode_hex_bytes(input: &str) -> Vec<u8> {
    let mut bytes = Vec::new();
    for chunk in input.as_bytes().chunks(2) {
        if chunk.len() != 2 {
            break;
        }
        if let Ok(hex) = std::str::from_utf8(chunk) {
            if let Ok(byte) = u8::from_str_radix(hex, 16) {
                bytes.push(byte);
            }
        }
    }
    bytes
}

/// RU: Форматирует address/register value в каноническом 8-digit hex style.
/// EN: Formats an address/register value in the canonical eight-digit hex style.
///
/// RU: Единый формат упрощает сравнение status panels, logs и hexdumps.
/// EN: Consistent formatting makes status panels, logs, and hexdumps easy to compare.
pub fn format_addr(value: u32) -> String {
    format!("{value:#010x}")
}

/// RU: Форматирует bytes как классический address/hex/ASCII memory dump.
/// EN: Formats bytes as a classic address/hex/ASCII memory dump.
///
/// RU: Это только presentation helper: он не владеет состоянием памяти, а лишь
/// RU: рисует byte slice, уже полученный из bridge dump response.
/// EN: This is a presentation helper only: it does not own memory state, it only
/// EN: renders the byte slice already captured from a bridge dump response.
pub fn format_hexdump(start_addr: u32, bytes: &[u8]) -> String {
    bytes
        .chunks(16)
        .enumerate()
        .map(|(row, chunk)| {
            let address = start_addr + (row as u32 * 16);
            let hex = chunk
                .iter()
                .map(|byte| format!("{byte:02x}"))
                .collect::<Vec<_>>()
                .join(" ");
            let ascii = chunk
                .iter()
                .map(|byte| {
                    if byte.is_ascii_graphic() || *byte == b' ' {
                        *byte as char
                    } else {
                        '.'
                    }
                })
                .collect::<String>();
            format!("{address:#010x}: {hex:<47} |{ascii}|")
        })
        .collect::<Vec<_>>()
        .join("\n")
}
