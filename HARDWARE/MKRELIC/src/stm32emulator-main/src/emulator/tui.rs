use std::time::{Duration, Instant};

use anyhow::Result;
use crossterm::{
    event::{self, Event, KeyCode, KeyEventKind, KeyModifiers},
    execute,
    terminal::{EnterAlternateScreen, LeaveAlternateScreen, disable_raw_mode, enable_raw_mode},
};
use ratatui::{DefaultTerminal, Frame};

use crate::tui::render_frame;

use super::{BoardView, EmulatorRuntime};

/// RU: Запускает интерактивный terminal UI до выхода пользователя.
/// EN: Runs the interactive terminal UI until the user exits.
///
/// RU: Цикл намеренно простой: обновить bridge state, снять board snapshot,
/// RU: отрисовать immutable snapshot, затем превратить одно key event в команду.
/// EN: The loop is deliberately simple: refresh bridge state, take a board snapshot,
/// EN: render that immutable snapshot, then translate one key event into a command.
pub fn run_tui(runtime: &mut EmulatorRuntime) -> Result<()> {
    let mut tui = TuiGuard::enter()?;
    let mut app = TuiApp::default();
    let mut last_status_refresh = Instant::now() - Duration::from_secs(1);

    loop {
        if last_status_refresh.elapsed() >= Duration::from_millis(500) {
            runtime.request_status();
            last_status_refresh = Instant::now();
        }

        let summary = runtime.view();
        tui.terminal.draw(|frame| draw(frame, &summary, &app))?;

        if !event::poll(Duration::from_millis(100))? {
            continue;
        }

        let Event::Key(key) = event::read()? else {
            continue;
        };
        if key.kind != KeyEventKind::Press {
            continue;
        }

        match key.code {
            KeyCode::Esc => break,
            KeyCode::Char('c') if key.modifiers.contains(KeyModifiers::CONTROL) => break,
            KeyCode::Char('j') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                submit_input(runtime, &mut app, &mut last_status_refresh);
            }
            KeyCode::Enter => {
                submit_input(runtime, &mut app, &mut last_status_refresh);
            }
            KeyCode::Backspace => {
                app.input.pop();
            }
            KeyCode::Char(ch) => {
                app.input.push(ch);
            }
            _ => {}
        }
    }

    Ok(())
}

/// RU: Рисует один frame из уже подготовленного UI state.
/// EN: Draws one frame from already prepared UI state.
///
/// RU: Тонкий wrapper делает ownership boundary очевидной: render получает
/// RU: `BoardView`, а не mutable runtime, который владеет внешним процессом.
/// EN: Keeping this as a thin wrapper makes the ownership boundary obvious:
/// EN: rendering receives a `BoardView`, not the mutable runtime owning the process.
fn draw(frame: &mut Frame<'_>, summary: &BoardView, app: &TuiApp) {
    render_frame::render(frame, summary, &app.input, &app.history);
}

fn submit_input(
    runtime: &mut EmulatorRuntime,
    app: &mut TuiApp,
    last_status_refresh: &mut Instant,
) {
    let input = app.input.trim().to_string();
    let output = runtime.exec_command(&input);
    if !input.is_empty() {
        app.history.push(format!("$ {input}"));
    }
    if !output.is_empty() {
        app.last_feedback = Some(output.clone());
        app.history.push(output);
    }
    app.input.clear();
    *last_status_refresh = Instant::now();
    trim_history(&mut app.history);
}

/// RU: Держит in-memory command history ограниченной по размеру.
/// EN: Keeps the in-memory command history bounded.
///
/// RU: TUI может работать долго; trimming старых строк предотвращает unbounded
/// RU: memory growth и сохраняет свежий operator context.
/// EN: The TUI can run for a long session; trimming old rows prevents unbounded
/// EN: memory growth while preserving the most recent operator context.
fn trim_history(history: &mut Vec<String>) {
    const LIMIT: usize = 100;
    if history.len() > LIMIT {
        let overflow = history.len() - LIMIT;
        history.drain(0..overflow);
    }
}

#[derive(Default)]
struct TuiApp {
    input: String,
    last_feedback: Option<String>,
    history: Vec<String>,
}

struct TuiGuard {
    terminal: DefaultTerminal,
}

impl TuiGuard {
    /// RU: Переключает terminal в alternate-screen raw mode и создает ratatui state.
    /// EN: Switches the terminal into alternate-screen raw mode and creates ratatui state.
    ///
    /// RU: `TuiGuard` владеет cleanup path через `Drop`, поэтому callers могут
    /// RU: свободно использовать `?` после входа в UI и не ломать terminal.
    /// EN: `TuiGuard` owns the cleanup path through `Drop`, so callers can use `?`
    /// EN: freely after entering the UI without leaving the terminal broken.
    fn enter() -> Result<Self> {
        enable_raw_mode()?;
        execute!(std::io::stdout(), EnterAlternateScreen)?;
        let terminal = ratatui::init();
        Ok(Self { terminal })
    }
}

impl Drop for TuiGuard {
    /// RU: Восстанавливает terminal mode даже при выходе через `?` или panic unwind.
    /// EN: Restores terminal mode even when the TUI exits through `?` or a panic unwind.
    ///
    /// RU: Raw mode и alternate screen — process-global terminal settings, поэтому
    /// RU: cleanup должен быть в `Drop`, а не дублироваться в каждой точке выхода.
    /// EN: Raw mode and alternate screen are process-global terminal settings, so
    /// EN: cleanup belongs in `Drop` instead of being duplicated at every return site.
    fn drop(&mut self) {
        let _ = disable_raw_mode();
        let _ = execute!(std::io::stdout(), LeaveAlternateScreen);
        ratatui::restore();
    }
}
