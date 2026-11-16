// error::Error нужен, чтобы main мог вернуть почти любую ошибку в одном типе.
// io нужен для доступа к stdout.
use std::{error::Error, io};

use crossterm::{
    // Эти события включают / выключают передачу мыши терминалу.
    event::{DisableMouseCapture, EnableMouseCapture},
    // execute! отправляет управляющие команды терминалу.
    execute,
    // AlternateScreen = отдельный экран терминала для TUI.
    // После выхода обычный экран пользователя восстанавливается.
    terminal::{EnterAlternateScreen, LeaveAlternateScreen},
};
// Импортируем состояние приложения и главный event loop.
use ctos_monitor::application::{app::App, run::run_app};
use ratatui::{
    Terminal,
    // raw mode нужен, чтобы кнопки читались сразу, без Enter и без эха в терминал.
    crossterm::terminal::{disable_raw_mode, enable_raw_mode},
    prelude::CrosstermBackend,
};

// #[tokio::main] создаёт async-runtime и позволяет писать async fn main().
/// Назначение: инициализировать терминал, запустить TUI и корректно восстановить консоль при выходе.
#[tokio::main]
async fn main() -> Result<(), Box<dyn Error>> {
    // Включаем raw mode для TUI.
    enable_raw_mode()?;
    // Берём stdout, чтобы рисовать в терминал.
    let mut stdout = io::stdout();
    // Переходим на альтернативный экран и включаем мышь.
    execute!(stdout, EnterAlternateScreen, EnableMouseCapture)?;
    // Оборачиваем stdout в backend для ratatui.
    let backend = CrosstermBackend::new(stdout);
    // Создаём сам Terminal.
    let mut terminal = Terminal::new(backend)?;
    // Создаём состояние приложения.
    let mut app = App::new();
    // Запускаем главный цикл приложения и ждём его завершения.
    let res = run_app(&mut terminal, &mut app).await;

    // Ниже идёт обязательная уборка терминала после выхода из TUI.
    disable_raw_mode()?;
    execute!(
        terminal.backend_mut(),
        LeaveAlternateScreen,
        DisableMouseCapture
    )?;
    terminal.show_cursor()?;
    // Если run_app завершился ошибкой, печатаем её уже в обычный терминал.
    if let Err(e) = res {
        println!("{}", e);
    }
    Ok(())
}
