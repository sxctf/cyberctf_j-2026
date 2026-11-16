// error::Error нужен для ограничения на тип ошибки backend в generic-функции.
// io нужен для io::Result и io::Error.
// Duration нужен для настройки таймера redraw/event-loop.
use std::{error::Error, io, time::Duration};

// Импортируем состояние приложения и функцию рисования UI.
use crate::{application::app::App, ui::ui::ui};
// EventStream = асинхронный поток событий клавиатуры / мыши.
// KeyCode / KeyModifiers / KeyEventKind помогают разбирать конкретные клавиши.
use crossterm::event::{Event, EventStream, KeyCode, KeyEventKind, KeyModifiers};
// StreamExt нужен для метода .next() на потоке событий.
use futures::StreamExt;
// Terminal - сам объект терминала.
// Backend - обобщённый тип движка отрисовки.
use ratatui::{Terminal, prelude::Backend};
// interval создаёт периодический таймер для tokio::select!.
use tokio::time::interval;

// Главный цикл приложения.
// B: Backend значит: функция умеет работать с любым backend ratatui.
/// Назначение: крутить главный цикл TUI, читать клавиши и обновлять состояние приложения.
pub async fn run_app<B: Backend>(terminal: &mut Terminal<B>, app: &mut App) -> io::Result<()>
where
    // Это ограничение нужно, чтобы ошибку backend можно было безопасно превратить в io::Error.
    B::Error: Error + Send + Sync + 'static,
{
    // Таймер тикает раз в 100 мс.
    // Даже если пользователь ничего не нажимает, цикл всё равно периодически просыпается.
    let mut tick_rate = interval(Duration::from_millis(100));
    // Создаём поток событий терминала.
    let mut stream_reader = EventStream::new();

    // Бесконечный цикл: рисуем экран, ждём событие, меняем состояние, снова рисуем.
    loop {
        // terminal.draw вызывает нашу функцию ui(...) и просит ratatui перерисовать кадр.
        // map_err(io::Error::other) переводит ошибку backend в io::Error.
        terminal
            .draw(|frame| ui(frame, app))
            .map_err(io::Error::other)?;

        // tokio::select! ждёт сразу несколько async-событий и выполняет первое, которое готово.
        tokio::select! {
            // Ветка таймера. Здесь логики нет, но она keeps loop alive.
            _ = tick_rate.tick() => {
                // На каждом тике чуть-чуть поворачиваем радар, чтобы карта анимировалась.
                app.advance_radar();
            }
            // Ветка чтения следующего терминального события.
            maybe_event = stream_reader.next() => {
                match maybe_event {
                    // Нас интересуют только события нажатия клавиши.
                    Some(Ok(Event::Key(key))) if key.kind == KeyEventKind::Press => {
                        // Разбираем одновременно модификаторы (Ctrl/Shift/...) и код клавиши.
                        match (key.modifiers, key.code) {
                            // Ctrl-C завершает программу.
                            (KeyModifiers::CONTROL, KeyCode::Char('c') | KeyCode::Char('C')) => app.quit(),
                            // Если включён W-режим (inject callback), клавиши идут в hex-поле.
                            _ if app.awaiting_callback_address() => match key.code {
                                // Esc отменяет режим.
                                KeyCode::Esc => app.cancel_write_callback_mode(),
                                // Enter применяет введённый hex-адрес.
                                KeyCode::Enter => { app.try_inject_callback_from_input(); }
                                // Backspace стирает последний символ.
                                KeyCode::Backspace => app.backspace_callback_hex_input(),
                                // Принимаем hex-цифры и 'x' для префикса "0x".
                                KeyCode::Char(ch) => app.push_callback_hex_char(ch),
                                _ => {}
                            },
                            // Если включён Rename Mode, клавиши трактуем как редактирование нового имени.
                            _ if app.awaiting_rename() => match key.code {
                                // Esc отменяет переименование.
                                KeyCode::Esc => app.cancel_rename_mode(),
                                // Enter применяет новое имя к выбранному устройству.
                                KeyCode::Enter => {
                                    app.try_rename_selected_from_input();
                                }
                                // Backspace стирает последний символ.
                                KeyCode::Backspace => app.backspace_rename_input(),
                                // Space добавляет пробел в имя.
                                KeyCode::Char(ch) => app.push_rename_char(ch),
                                // Всё остальное в этом режиме игнорируем.
                                _ => {}
                            },
                            // Если включён Add Mode, почти все клавиши трактуем как ввод номера устройства.
                            _ if app.awaiting_device_type() => match key.code {
                                // Esc отменяет ввод типа устройства.
                                KeyCode::Esc => app.cancel_add_mode(),
                                // Enter подтверждает ввод.
                                KeyCode::Enter => {
                                    app.try_add_device_from_input();
                                }
                                // Backspace стирает последнюю цифру.
                                KeyCode::Backspace => app.backspace_device_type_input(),
                                // Разрешаем только ASCII-цифры 0..9.
                                KeyCode::Char(ch) if ch.is_ascii_digit() => app.push_device_type_digit(ch),
                                // Всё остальное в этом режиме игнорируем.
                                _ => {}
                            },
                            // Обычный режим: A включает Add Mode.
                            (_, KeyCode::Char('a') | KeyCode::Char('A')) => app.start_add_mode(),
                            // R включает Rename Mode для выбранного устройства.
                            (_, KeyCode::Char('r') | KeyCode::Char('R')) => app.start_rename_mode(),
                            // D удаляет выбранное устройство.
                            (_, KeyCode::Char('d') | KeyCode::Char('D')) => app.delete_selected(),
                            // P pin'ит выбранное устройство.
                            (_, KeyCode::Char('p') | KeyCode::Char('P')) => app.pin_selected_device(),
                            (_, KeyCode::Char('l') | KeyCode::Char('L')) => app.trigger_selected_log(),
                            // W открывает режим инъекции callback-адреса (remote UAF exploit без GDB).
                            (_, KeyCode::Char('w') | KeyCode::Char('W')) => app.start_write_callback_mode(),
                            // Стрелка вниз двигает выделение.
                            (_, KeyCode::Down) => app.select_next(),
                            // Стрелка вверх двигает выделение назад.
                            (_, KeyCode::Up) => app.select_previous(),
                            // Q и Esc завершают приложение в обычном режиме.
                            (_, KeyCode::Char('q') | KeyCode::Char('Q') | KeyCode::Esc) => app.quit(),
                            // Все прочие клавиши нам не нужны.
                            _ => {}
                        }
                    }
                    // Другие типы событий (мышь, resize и т.д.) сейчас просто игнорируем.
                    Some(Ok(_)) => {}
                    // Если чтение событий сломалось, выходим с ошибкой.
                    Some(Err(err)) => return Err(err),
                    // None означает, что поток событий закрылся.
                    None => return Ok(()),
                }
            }
        }

        // После обработки событий проверяем, не попросили ли приложение завершиться.
        if app.should_quit() {
            return Ok(());
        }
    }
}
