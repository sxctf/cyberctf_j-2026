use ratatui::{
    Frame,
    layout::{Constraint, Direction, Layout},
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Paragraph, Wrap},
};

use crate::{
    emulator::BoardView,
    tui::{board_panel::render_board_panel, state_panel::render_state_panel},
};

pub(crate) fn render(frame: &mut Frame, summary: &BoardView, input: &str, history: &[String]) {
    let area = frame.area();
    let layout = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3),
            Constraint::Min(8),
            Constraint::Length(3),
        ])
        .split(area);
    let header_area = layout[0];
    let body_area = layout[1];
    let input_area = layout[2];

    let header = Paragraph::new(Line::from(vec![
        Span::styled(
            format!(" {} ", summary.title),
            Style::default()
                .fg(Color::Cyan)
                .add_modifier(Modifier::BOLD),
        ),
        Span::raw(format!(
            " challenge={} step={} TIM2_CNT={:#010x} service_mode={} ",
            summary.challenge.slug(),
            summary.step,
            summary.tim2_cnt,
            summary.service_mode
        )),
    ]))
    .block(Block::default().borders(Borders::ALL).title(" STM32 Lab "));

    frame.render_widget(header, header_area);

    if body_area.width < 106 {
        let board_inner_height = body_area.height.saturating_sub(2);
        let board_panel = Paragraph::new(render_board_panel(summary, board_inner_height))
            .wrap(Wrap { trim: false })
            .block(
                Block::default()
                    .borders(Borders::ALL)
                    .title(" STM32 Emulator Board "),
            );
        frame.render_widget(board_panel, body_area);
        render_input_bar(frame, input, input_area);
        return;
    }

    let body_columns = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Length(68), Constraint::Min(36)])
        .split(body_area);

    let board_inner_height = body_columns[0].height.saturating_sub(2);
    let board_panel = Paragraph::new(render_board_panel(summary, board_inner_height))
        .wrap(Wrap { trim: false })
        .style(Style::default().fg(Color::Green))
        .block(
            Block::default()
                .borders(Borders::ALL)
                .title(" STM32 Emulator Board "),
        );
    frame.render_widget(board_panel, body_columns[0]);

    let right_rows = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(10),
            Constraint::Percentage(45),
            Constraint::Min(8),
        ])
        .split(body_columns[1]);

    // Формируем краткую сводку runtime-состояния.
    let state = Paragraph::new(render_state_panel(summary))
        .wrap(Wrap { trim: false })
        .block(
            Block::default()
                .borders(Borders::ALL)
                .title(" Runtime State "),
        );
    // Рисуем правую state-панель.
    frame.render_widget(state, right_rows[0]);

    // Верхний рабочий ряд делим на watch и UART.
    let top_row = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(58), Constraint::Percentage(42)])
        .split(right_rows[1]);

    // Формируем окно watch dump.
    let watch = Paragraph::new(summary.watch_dump.clone())
        .wrap(Wrap { trim: false })
        .block(Block::default().borders(Borders::ALL).title(" Watch "));
    // Рисуем watch-панель.
    frame.render_widget(watch, top_row[0]);

    // Формируем окно UART лога.
    let uart_text = tail_lines(&summary.uart_log, top_row[1].height.saturating_sub(2));
    let uart = Paragraph::new(uart_text)
        .wrap(Wrap { trim: false })
        .block(Block::default().borders(Borders::ALL).title(" UART "));
    // Рисуем UART лог.
    frame.render_widget(uart, top_row[1]);

    // Нижний ряд делим на Emulator Log и Command Log.
    let bottom_row = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(65), Constraint::Percentage(35)])
        .split(right_rows[2]);

    // Формируем окно лога эмулятора/bridge-а.
    let emulator_text = tail_lines(
        &summary.emulator_log,
        bottom_row[0].height.saturating_sub(2),
    );
    let emulator_log = Paragraph::new(emulator_text)
        .wrap(Wrap { trim: false })
        .block(
            Block::default()
                .borders(Borders::ALL)
                .title(" Emulator Log (latest) "),
        );
    // Рисуем лог эмулятора.
    frame.render_widget(emulator_log, bottom_row[0]);

    // RU: Объединяем runtime command_log с локальной TUI-историей, но держим
    // RU: локальную историю последней. Так shortcuts из runtime остаются видимыми,
    // RU: а результат только что введенной команды не вытесняется служебными
    // RU: строками `> :bridge ...` после заполнения панели Command Feedback.
    // EN: Merge runtime command_log with local TUI history, keeping local history
    // EN: last. This keeps shortcut commands visible while preventing service
    // EN: `> :bridge ...` rows from pushing the latest manual command result out
    // EN: of the filled Command Feedback panel.
    let command_text = command_feedback_text(
        history,
        &summary.command_log,
        bottom_row[1].height.saturating_sub(2),
    );
    let commands = Paragraph::new(command_text)
        .wrap(Wrap { trim: false })
        .block(
            Block::default()
                .borders(Borders::ALL)
                .title(" Command Feedback "),
        );
    // Рисуем историю команд.
    frame.render_widget(commands, bottom_row[1]);

    render_input_bar(frame, input, input_area);
}

fn render_input_bar(frame: &mut Frame, input: &str, input_area: ratatui::layout::Rect) {
    // let visible_text = if input.is_empty() {
    //     feedback
    //         .map(|line| format!("last: {}", one_line(line)))
    //         .unwrap_or_else(|| "type a command and press Enter".to_string())
    // } else {
    //     input.to_string()
    // };
    let visible_text = input.to_string();
    let input_bar = Paragraph::new(visible_text)
        .block(Block::default().borders(Borders::ALL).title(
            " Input | status | uart <text> | step <n> | dump <addr> <len> | dumpchunk <addr> <len> | regs | pin set <pin> <0|1> | reset ",
        ))
        .style(Style::default().fg(Color::Yellow));
    frame.render_widget(input_bar, input_area);
    frame.set_cursor_position((input_area.x + input.len() as u16 + 1, input_area.y + 1));
}

// fn one_line(input: &str) -> String {
//     input.lines().next().unwrap_or_default().to_string()
// }

fn command_feedback_lines<'a>(history: &'a [String], command_log: &'a [String]) -> Vec<&'a str> {
    command_log
        .iter()
        .chain(history.iter())
        .map(String::as_str)
        .collect()
}

fn command_feedback_text(history: &[String], command_log: &[String], max_lines: u16) -> String {
    // RU: Режем Command Feedback по реальным terminal-строкам, а не по записям
    // RU: истории. Результаты вроде `status` многострочные; если считать такой
    // RU: результат одной записью, хвост панели выбирается неверно и вывод команды
    // RU: визуально сдвигается вниз при обновлениях.
    // EN: Trim Command Feedback by real terminal rows, not by history entries.
    // EN: Outputs such as `status` are multi-line; treating them as one entry makes
    // EN: tail selection wrong and the command output appears to drift downward.
    let rows = command_feedback_lines(history, command_log)
        .into_iter()
        .flat_map(str::lines)
        .collect::<Vec<_>>();

    tail_line_refs(&rows, max_lines)
}

fn tail_line_refs(lines: &[&str], max_lines: u16) -> String {
    let max_lines = max_lines as usize;
    if max_lines == 0 {
        return String::new();
    }

    let start = lines.len().saturating_sub(max_lines);
    lines[start..].join("\n")
}

fn tail_lines(lines: &[String], max_lines: u16) -> String {
    let max_lines = max_lines as usize;
    if max_lines == 0 {
        return String::new();
    }

    let start = lines.len().saturating_sub(max_lines);
    lines[start..].join("\n")
}

#[cfg(test)]
mod tests {
    use super::{command_feedback_lines, command_feedback_text, tail_lines};

    #[test]
    fn tail_lines_keeps_latest_entries() {
        let lines = ["old", "middle", "new"]
            .into_iter()
            .map(String::from)
            .collect::<Vec<_>>();

        assert_eq!(tail_lines(&lines, 2), "middle\nnew");
    }

    #[test]
    fn command_feedback_merges_ui_history_and_runtime_log() {
        let history = vec!["$ status".to_string(), "bridge_state=Connected".to_string()];
        let command_log = vec![
            "> :bridge status".to_string(),
            "> :bridge step 1".to_string(),
        ];

        assert_eq!(
            command_feedback_lines(&history, &command_log),
            vec![
                "> :bridge status",
                "> :bridge step 1",
                "$ status",
                "bridge_state=Connected"
            ]
        );
    }

    #[test]
    fn command_feedback_tails_multiline_output_by_visible_rows() {
        let history = vec![
            "$ status".to_string(),
            "bridge_state=Connected\nstep=1\nstatus=ready".to_string(),
        ];
        let command_log = vec!["> :bridge status".to_string()];

        assert_eq!(
            command_feedback_text(&history, &command_log, 3),
            "bridge_state=Connected\nstep=1\nstatus=ready"
        );
    }
}
