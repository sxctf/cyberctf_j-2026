use crate::emulator::BoardView;

pub(crate) fn render_state_panel(summary: &BoardView) -> String {
    let mut lines = vec![
        format!("Brief: {}", truncate_line(&summary.brief, 46)),
        format!("Status: {}", truncate_line(&summary.status_line, 45)),
        format!("GPIOA_IDR: {:#06x}", summary.gpioa_idr),
        format!("GPIOA_ODR: {:#06x}", summary.gpioa_odr),
        format!("Manifest present: {}", summary.manifest_present),
        format!("Service latch: {:#010x}", summary.service_latch),
        format!("Flag SRAM lock: {}", summary.flag_window_locked),
        format!("Armed ticks left: {}", summary.armed_ticks_left),
    ];

    if summary.challenge.slug() == "glitch" {
        lines.push("Path: uart probe -> step 33 -> toggle PA0".to_string());
    } else {
        lines.push("Path: inspect SRAM manifest and rebuild fragments".to_string());
    }

    lines.join("\n")
}

fn truncate_line(input: &str, max_chars: usize) -> String {
    if input.chars().count() <= max_chars {
        return input.to_string();
    }

    if max_chars <= 3 {
        return input.chars().take(max_chars).collect();
    }

    let mut output = input.chars().take(max_chars - 3).collect::<String>();
    output.push_str("...");
    output
}

#[cfg(test)]
mod tests {
    use super::truncate_line;

    #[test]
    fn truncate_line_handles_utf8_boundaries() {
        assert_eq!(truncate_line("Привет, мир", 8), "Приве...");
    }

    #[test]
    fn truncate_line_keeps_short_utf8_text() {
        assert_eq!(truncate_line("Статус", 10), "Статус");
    }
}
