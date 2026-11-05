use rand::RngExt;

use crate::emulator::BoardView;

const BOARD_SCHEMA: &str = r#"
╔═════════════════════════════════════════════════╗
║          STM32F407VGT6  LQFP-100                ║
╠═════════════════════════════════════════════════╣
║ PE2─┤1  ┌───────────────────────┐  76├─PA14 swc ║
║ PE3─┤2  │  Cortex-M4F  168MHz   │  75├─PA13 swd ║
║ PE4─┤3  │  1MB Flash  192K RAM  │  74├─PA12 usb ║
║ PE5─┤4  │  FPU  DSP  ART Accel  │  73├─PA11 usb ║
║ PE6─┤5  │                       │  72├─PA10 rx1 ║
║VBAT─┤6  │  GPIO:A-I   TIM:x14  │   71├─PA9  tx1 ║
║PC13─┤7  │  ADC:x3     DAC:x2   │   70├─PA8      ║
║PC14─┤8  │  UART:x6    SPI:x3   │   69├─PC9      ║
║PC15─┤9  │  I2C:x3     CAN:x2   │   68├─PC8      ║
║ VSS─┤10 │  USB:OTG    DMA:x2   │   67├─PC7      ║
║ VDD─┤11 │  ETH SDIO DCMI CRC   │   66├─PC6      ║
║ PH0─┤12 └───────────────────────┘  65├─PD15     ║
║ PH1─┤13                            64├─PD14     ║
║NRST─┤14    VDD─┤├─100n─GND         63├─PD13     ║
║ PC0─┤15                            62├─PD12     ║
║ PC1─┤16                            61├─PD11     ║
║ PC2─┤17                            60├─PD10     ║
║ PC3─┤18                            59├─PD9  rx3 ║
║ VDD─┤19                            58├─PD8  tx3 ║
║ VSS─┤20                            57├─PB15     ║
║ PA0─┤21 wkup                       56├─PB14     ║
║ PA1─┤22                            55├─PB13     ║
║ PA2─┤23 tx2                        54├─PB12     ║
║ PA3─┤24 rx2                    VSS 53├─         ║
║ VDD─┤25                        VDD 52├─         ║
║ PA4─┤26 dac1                  PB11 51├─ i2c     ║
║ PA5─┤27 dac2                  PB10 50├─ i2c     ║
║ PA6─┤28                       PE15 49├─         ║
║ PA7─┤29                       PE14 48├─         ║
║ PC4─┤30                       PE13 47├─         ║
║ PC5─┤31                       PE12 46├─         ║
║ PB0─┤32                       PE11 45├─         ║
║ PB1─┤33                       PE10 44├─         ║
║ PB2─┤34 boot1                  PE9 43├─         ║
║ PE7─┤35                        PE8 42├─         ║
║ PE8─┤36                        VSS 41├─         ║
║ VSS─┤37                        VDD 40├─         ║
║ VDD─┤38                        PE7 39├─         ║
╠═════════════════════════════════════════════════╣
║ BTN:{BTN}  LED:{LED}  SVC:{SVC}   FLT:{FLT}     ║
║ {UART_RX} ║
║ {UART_TX} ║
╠═════════════════════════════════════════════════╣
║ HSE:12/13  LSE:8/9  DBG:75/76   BOOT0:94        ║
║ VDD:{VDD}V   Temp:{TEMP}°C    100pins          ║
╚═════════════════════════════════════════════════╝
"#;

const COMPACT_BOARD_SCHEMA: &str = r#"
╔═════════════════════════════════════════════════╗
║          STM32F407VGT6  LQFP-100                ║
╠═════════════════════════════════════════════════╣
║ PA0 wkup  BTN:{BTN}        PA5 dac2  LED:{LED}  ║
║ GPIOA_IDR:{GPIOA_IDR}      GPIOA_ODR:{GPIOA_ODR} ║
║ TIM2_CNT:{TIM2_CNT}        STEP:{STEP}           ║
╠═════════════════════════════════════════════════╣
║ Core: Cortex-M4F 168MHz | Flash 1MB | RAM 192K  ║
║ Periph: GPIO A-I | TIM x14 | UART x6 | SPI x3   ║
║ Debug: SWD PA13/PA14 | BOOT0:94 | NRST:14       ║
╠═════════════════════════════════════════════════╣
║ SVC:{SVC}  FLT:{FLT}  Challenge:{CHALLENGE}     ║
║ {UART_RX} ║
║ {UART_TX} ║
╚═════════════════════════════════════════════════╝
"#;

pub(crate) fn render_board_panel(summary: &BoardView, max_lines: u16) -> String {
    let schema = if max_lines as usize >= board_schema_line_count(BOARD_SCHEMA) {
        BOARD_SCHEMA
    } else {
        COMPACT_BOARD_SCHEMA
    };

    let button = if summary.pa0_high { "HIGH" } else { "LOW " };
    let led = if summary.pa5_led_on { "ON " } else { "OFF" };
    let service = if summary.service_mode {
        "UNLOCKED"
    } else {
        "LOCKED  "
    };
    let fault = if summary.fault_window_open {
        "OPEN "
    } else if summary.armed_ticks_left > 0 {
        "ARMED"
    } else {
        "IDLE "
    };

    let last_rx = summary.last_uart_rx.as_deref().unwrap_or("<none>");
    let last_tx = summary.last_uart_tx.as_deref().unwrap_or("<none>");

    let uart_rx = truncate_chars(&format!("uart.rx: {last_rx:<39}"), 47);
    let uart_tx = truncate_chars(&format!("uart.tx: {last_tx:<39}"), 47);

    let mut rng = rand::rng();
    let vdd = rng.random_range(2.0..=3.7);
    let temp = rng.random_range(38.199..=39.999);

    let rendered = schema
        .replace("{BTN}", button)
        .replace("{LED}", led)
        .replace("{SVC}", service)
        .replace("{FLT}", fault)
        .replace("{GPIOA_IDR}", &format!("{:#06x}", summary.gpioa_idr))
        .replace("{GPIOA_ODR}", &format!("{:#06x}", summary.gpioa_odr))
        .replace("{TIM2_CNT}", &format!("{:#010x}", summary.tim2_cnt))
        .replace("{STEP}", &format!("{:<10}", summary.step))
        .replace("{CHALLENGE}", summary.challenge.slug())
        .replace("{UART_RX}", &uart_rx)
        .replace("{UART_TX}", &uart_tx)
        .replace("{VDD}", &format!("{:.1}", vdd))
        .replace("{TEMP}", &format!("{:.1}", temp));

    expand_board_width(&rendered)
}

fn expand_board_width(schema: &str) -> String {
    const TARGET_WIDTH: usize = 64;

    schema
        .trim_matches('\n')
        .lines()
        .map(|line| {
            let width = line.chars().count();
            if width >= TARGET_WIDTH {
                return line.to_string();
            }

            if let Some(prefix) = line.strip_suffix('╗') {
                return format!("{prefix}{}╗", "═".repeat(TARGET_WIDTH - width));
            }
            if let Some(prefix) = line.strip_suffix('╣') {
                return format!("{prefix}{}╣", "═".repeat(TARGET_WIDTH - width));
            }
            if let Some(prefix) = line.strip_suffix('╝') {
                return format!("{prefix}{}╝", "═".repeat(TARGET_WIDTH - width));
            }
            if let Some(prefix) = line.strip_suffix('║') {
                return format!("{prefix}{}║", " ".repeat(TARGET_WIDTH - width));
            }

            line.to_string()
        })
        .collect::<Vec<_>>()
        .join("\n")
}

fn truncate_chars(input: &str, max_chars: usize) -> String {
    input.chars().take(max_chars).collect()
}

fn board_schema_line_count(schema: &str) -> usize {
    schema.trim_matches('\n').lines().count()
}

#[cfg(test)]
mod tests {
    use super::{
        BOARD_SCHEMA, COMPACT_BOARD_SCHEMA, board_schema_line_count, expand_board_width,
        truncate_chars,
    };

    #[test]
    fn truncate_chars_handles_utf8_boundaries() {
        assert_eq!(truncate_chars("uart.rx: привет", 12), "uart.rx: при");
    }

    #[test]
    fn compact_board_is_shorter_than_full_board() {
        assert!(
            board_schema_line_count(COMPACT_BOARD_SCHEMA) < board_schema_line_count(BOARD_SCHEMA)
        );
    }

    #[test]
    fn expanded_board_has_consistent_width() {
        let expanded = expand_board_width(COMPACT_BOARD_SCHEMA);
        assert!(expanded.lines().all(|line| line.chars().count() == 64));
    }
}
