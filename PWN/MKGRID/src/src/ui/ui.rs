// Здесь лежит вся визуальная часть интерфейса.
// Важно: ui.rs НЕ должен решать бизнес-логику. Он только смотрит на App и рисует.
use ratatui::{
    // Frame - "холст" текущего кадра. Через него рисуются виджеты.
    Frame,
    layout::{Constraint, Direction, Layout, Rect},
    style::{Color, Style},
    symbols::Marker,
    text::Line,
    widgets::{
        Block, BorderType, Borders, List, ListItem, Padding, Paragraph,
        canvas::{Canvas, Circle, Line as canLine, Points, Rectangle},
    },
};

// UI читает данные из состояния приложения.
use crate::application::app::App;

// Небольшой модуль с цветовой темой.
// Так удобнее, чем писать Color::Rgb(...) по всему файлу.
mod theme {
    use ratatui::style::Color;

    pub const PRIMARY: Color = Color::Rgb(0, 255, 255);
    pub const SECONDARY: Color = Color::Rgb(138, 43, 226);
    pub const ACCENT: Color = Color::Rgb(0, 255, 128);
    pub const WARNING: Color = Color::Rgb(255, 165, 0);
    pub const TEXT_DIM: Color = Color::Rgb(100, 100, 120);
    pub const TEXT_BRIGHT: Color = Color::Rgb(220, 220, 240);
}

// Главная функция отрисовки одного кадра.
/// Назначение: нарисовать весь интерфейс за один кадр.
pub fn ui(frame: &mut Frame, app: &mut App) {
    // Ниже классическая builder-цепочка ratatui.
    // Идея builder pattern: каждый вызов возвращает изменённый объект,
    // поэтому можно настраивать его шаг за шагом через точку.
    let chunks = Layout::default()
        // Layout::default() создаёт "пустой" layout с настройками по умолчанию.
        // Пока это просто заготовка без информации, как делить экран.
        .direction(Direction::Vertical)
        // direction(...) говорит, В КАКОМ направлении делить область.
        // Vertical = сверху вниз. Значит chunks[0], chunks[1], chunks[2]
        // будут расположены вертикально.
        .margin(1)
        // margin(1) оставляет отступ в 1 клетку со всех сторон.
        // Это нужно, чтобы контент не прилипал к самому краю терминала.
        .constraints([
            // constraints(...) задаёт правила, как делить пространство между частями.
            // Length(3) = ровно 3 строки высоты.
            Constraint::Length(3),
            // Min(10) = минимум 10 строк, но при необходимости может занять больше.
            Constraint::Min(10),
            // Footer тоже фиксированной высоты 3 строки.
            Constraint::Length(3),
        ])
        .split(frame.area());
    // split(frame.area()) применяет все правила layout к прямоугольнику всего кадра.
    // На выходе получаем массив/список прямоугольников chunks.

    // Рисуем три секции интерфейса в соответствующие области.
    render_header(frame, chunks[0], app);
    render_body(frame, chunks[1], app);
    render_footer(frame, chunks[2], app);
}

// Верхняя панель состояния.
/// Назначение: отрисовать верхнюю панель со статусом приложения и режимом ввода.
fn render_header(frame: &mut Frame, area: Rect, app: &App) {
    // selected = человекочитаемая строка про текущий выбор.
    let selected = app
        .selected_device()
        // map(...) запускается только если selected_device() вернул Some(...).
        // Здесь мы превращаем DeviceEntry в строку.
        .map(|device| format!("selected: {} ({})", device.name, device.device_type.label()))
        // unwrap_or_else(...) сработает, если selected_device() вернул None.
        // Тогда показываем строку-заглушку.
        .unwrap_or_else(|| "selected: none".to_owned());

    // status = вторая строка header.
    let status = if app.awaiting_callback_address() {
        // В W-режиме показываем накапливаемый hex-адрес.
        let current = if app.callback_hex_input.is_empty() {
            "_".to_owned()
        } else {
            app.callback_hex_input.clone()
        };
        format!(
            "INJECT MODE | enter hex addr for log_callback (e.g. 0x7f...b00) | current: {} | Enter injects | Esc cancels",
            current
        )
    } else if app.awaiting_rename() {
        // В режиме переименования показываем строку, которую пользователь сейчас редактирует.
        let current = if app.rename_input.is_empty() {
            "_".to_owned()
        } else {
            app.rename_input.clone()
        };
        format!(
            "RENAME MODE | edit current target name | current: {} | Enter confirms | Esc cancels",
            current
        )
    } else if app.awaiting_device_type() {
        // В режиме добавления показываем текущий ввод пользователя.
        let current = if app.device_type_input.is_empty() {
            "_".to_owned()
        } else {
            app.device_type_input.clone()
        };
        format!(
            "ADD MODE | type device number 1-18 | current: {} | Enter confirms | Esc cancels",
            current
        )
    } else if let Some(device) = &app.pinned_device {
        // Если есть pinned устройство, выводим краткую информацию о нём.
        format!(
            "PINNED {} ({}) at {:p}",
            device.name,
            device.device_type.label(),
            device.ptr
        )
    } else {
        // Иначе выводим подсказку по PWN-сценарию.
        "No pinned node. Pin one, then free it to inspect stale heap data.".to_owned()
    };

    // Paragraph::new(...) создаёт текстовый виджет.
    let header = Paragraph::new(vec![
        Line::from(format!(
            "ctOS Monitor | nodes: {} | {}",
            app.active_devices.len(),
            selected
        )),
        Line::from(status),
    ])
    .block(
        // .block(...) прикрепляет к Paragraph рамку и заголовок.
        Block::default()
            // Block::default() создаёт пустую рамку-заготовку.
            .title(" STATUS ")
            // title(...) задаёт текст в верхней части рамки.
            .borders(Borders::ALL)
            // borders(Borders::ALL) включает рамку со всех 4 сторон.
            .border_type(BorderType::Rounded)
            // border_type(...) меняет стиль углов и линий.
            // Rounded = скруглённые углы вместо прямых.
            .border_style(Style::default().fg(theme::PRIMARY)),
        // border_style(...) задаёт внешний вид рамки.
        // Style::default() = базовый стиль без настроек.
        // .fg(theme::PRIMARY) = цвет текста/рамки по foreground-цвету.
    );

    // render_widget(...) реально рисует виджет в выбранную прямоугольную область.
    frame.render_widget(header, area);
}

// Центральная часть экрана: слева список устройств, посередине наблюдаемость, справа карта.
/// Назначение: разделить центральную область на список устройств, телеметрию с логами и карту.
fn render_body(frame: &mut Frame, area: Rect, app: &mut App) {
    // Сначала режем всю центральную область на три вертикальные колонки.
    let chunks = Layout::default()
        // Создаём layout-заготовку для body-части интерфейса.
        .direction(Direction::Horizontal)
        // Horizontal = колонки пойдут слева направо.
        .constraints([
            // Левая колонка под список нод.
            Constraint::Percentage(30),
            // Средняя колонка под телеметрию и логи.
            Constraint::Percentage(30),
            // Правая колонка под карту города.
            Constraint::Percentage(40),
        ])
        // Применяем эти правила к прямоугольнику body-области.
        .split(area);

    // Теперь отдельно режем среднюю колонку пополам сверху вниз.
    let observability_chunks = Layout::default()
        // Vertical = части будут располагаться друг под другом.
        .direction(Direction::Vertical)
        // Отдаём верхнюю половину под телеметрию, а нижнюю под поток логов.
        .constraints([
            Constraint::Percentage(50),
            Constraint::Percentage(50),
        ])
        // Применяем vertical-layout только к средней колонке.
        .split(chunks[1]);

    // В левую колонку рисуем список активных устройств.
    render_nodes_list(frame, chunks[0], app);
    // В верхнюю половину средней колонки рисуем телеметрию по pinned pointer.
    render_telemetry(frame, observability_chunks[0], app);
    // В нижнюю половину средней колонки рисуем историю логов и вывод logger callback.
    render_logs(frame, observability_chunks[1], app);
    // В правую колонку по-прежнему рисуем карту города.
    render_map_city(frame, chunks[2], app);
}

// Левая панель со списком устройств.
/// Назначение: отрисовать левую панель со всеми активными устройствами.
fn render_nodes_list(frame: &mut Frame, area: Rect, app: &mut App) {
    // Собираем строки списка.
    let items: Vec<ListItem> = if app.active_devices.is_empty() {
        // Если элементов нет, показываем инструкцию.
        vec![ListItem::new(
            "No sessions allocated. Press A to open add mode.",
        )]
    } else {
        app.active_devices
            .iter()
            // iter() проходит по всем устройствам по ссылке.
            .map(|device| {
                // map(...) превращает каждый DeviceEntry в ListItem для UI.
                let pin = if app.is_pinned_ptr(device.ptr) {
                    " [PIN]"
                } else {
                    ""
                };
                ListItem::new(format!(
                    "#{:02}  {:<20} {:<22} {:p}{}",
                    device.id,
                    device.name,
                    device.device_type.label(),
                    device.ptr,
                    pin
                ))
            })
            .collect()
        // collect() собирает результаты map в готовый Vec<ListItem>.
    };

    // List::new(items) создаёт виджет списка из уже собранных строк.
    let list = List::new(items)
        .block(
            Block::default()
                .title(format!(" NODES [{}] ", app.active_devices.len()))
                .borders(Borders::ALL)
                .border_type(BorderType::Rounded)
                .border_style(Style::default().fg(theme::PRIMARY))
                .padding(Padding::horizontal(1)),
            // padding(...) добавляет внутренний отступ уже ВНУТРИ рамки.
            // horizontal(1) = по 1 клетке слева и справа.
        )
        .highlight_style(Style::default().bg(theme::PRIMARY).fg(Color::Black))
        // highlight_style(...) задаёт стиль выделенной строки.
        // bg(...) = цвет фона, fg(...) = цвет текста.
        .highlight_symbol("> ");
    // highlight_symbol(...) рисует маркер перед выбранным элементом.

    // render_stateful_widget нужен потому, что список хранит состояние выбора в app.list_state.
    frame.render_stateful_widget(list, area, &mut app.list_state);
}

// Верхняя половина средней панели: телеметрия / чтение памяти.
/// Назначение: показать содержимое pinned pointer и его текущее состояние в верхней половине observability-колонки.
fn render_telemetry(frame: &mut Frame, area: Rect, app: &App) {
    // Сразу вычисляем и содержимое текста, и цвет рамки.
    let (lines, border_color) = match &app.pinned_device {
        // Если pinned-устройство есть, рисуем подробную телеметрию по нему.
        Some(device) => {
            // Проверяем, жив ли pinned pointer или уже стал dangling после free.
            let state = if app.pinned_is_active() {
                ("live", theme::ACCENT)
            } else {
                ("freed / dangling", theme::WARNING)
            };
            // Читаем первые 32 байта по адресу freed extra_data-чанка, а не по session-чанку.
            // Именно тут у тяжёлых устройств после free появится unsorted-bin leak из libc.
            let bytes = unsafe { std::slice::from_raw_parts(device.heap_ptr as *const u8, 32) };
            // Здесь собираем все строки, которые попадут в Paragraph телеметрии.
            let mut lines = vec![
                // Первая строка показывает имя устройства.
                Line::from(format!("name: {}", device.name)),
                // Вторая строка показывает человекочитаемый и numeric тип.
                Line::from(format!(
                    "type: {} ({})",
                    device.device_type.label(),
                    u16::from(device.device_type)
                )),
                // Третья строка показывает внутренний id записи в TUI.
                Line::from(format!("id: {}", device.id)),
                // Четвёртая строка показывает адрес самой C-session.
                Line::from(format!("session: {:p}", device.ptr)),
                // Пятая строка показывает адрес extra_data-чанка, который читается в дампе.
                Line::from(format!("heap view: {:p}", device.heap_ptr)),
                // Шестая строка сообщает, live это память или уже freed/dangling.
                Line::from(format!("state: {}", state.0)),
                // Пустая строка визуально отделяет шапку от дампа памяти.
                Line::from(""),
                // Подпись перед hex dump.
                Line::from("raw freed-chunk bytes:"),
            ];
            // Добавляем к шапке hex dump из 32 байт памяти.
            lines.extend(format_hex_dump(bytes));
            // Возвращаем готовые строки и цвет рамки, связанный с текущим состоянием.
            (lines, state.1)
        }
        // Если pinned-устройства нет, показываем короткую инструкцию по шагам.
        None => (
            vec![
                // Сообщаем, что пока ничего не pinned.
                Line::from("No pinned device."),
                // Пустая строка отделяет заголовок от инструкции.
                Line::from(""),
                // Шаг 1: открыть add-mode.
                Line::from("1. Use A to enter add mode."),
                // Шаг 2: выбрать тип устройства.
                Line::from("2. Type a device number from 1 to 18 and press Enter."),
                // Шаг 3: выбрать созданную сессию стрелками.
                Line::from("3. Use Up/Down to select a session."),
                // Шаг 4: pinned + free для выхода в UAF-сценарий.
                Line::from("4. Press P to pin it, then D to free the same session."),
                // Шаг 5: читать stale extra_data chunk в этой же панели.
                Line::from("5. This panel will keep reading the pinned heap chunk."),
            ],
            // Когда pinned-устройства ещё нет, рамка спокойного тусклого цвета.
            theme::TEXT_DIM,
        ),
    };

    // Создаём текстовый виджет телеметрии.
    let telemetry = Paragraph::new(lines).block(
        Block::default()
            // Заголовок рамки верхней половины observability-панели.
            .title(" TELEMETRY ")
            // Включаем границы со всех сторон.
            .borders(Borders::ALL)
            // Используем закруглённый тип рамки.
            .border_type(BorderType::Rounded)
            // Цвет рамки зависит от того, live сейчас память или dangling.
            .border_style(Style::default().fg(border_color))
            // Даём внутренние отступы, чтобы текст не лип к краям.
            .padding(Padding::new(1, 1, 1, 1)),
    );

    // Рисуем готовый виджет в верхней половине средней колонки.
    frame.render_widget(telemetry, area);
}

// Нижняя половина средней панели: поток логов и реальный stdout от logger callback.
/// Назначение: показать историю действий и строки, которые были перехвачены из ctos_logger.
fn render_logs(frame: &mut Frame, area: Rect, app: &App) {
    // Высчитываем, сколько строк физически поместится в нижнюю панель с учётом рамки и padding.
    let max_visible = area.height.saturating_sub(4).max(1) as usize;
    // start = индекс первой видимой строки, чтобы показывать только хвост лога.
    let start = app.log_lines.len().saturating_sub(max_visible);
    // Превращаем хвост журнала в Vec<Line> для Paragraph.
    let lines: Vec<Line> = if app.log_lines.is_empty() {
        // Если журнал пуст, показываем понятную подсказку.
        vec![Line::from("No log entries yet. Press L/l on a selected node or pinned ghost.")]
    } else {
        app.log_lines[start..]
            .iter()
            // Каждую строку журнала превращаем в Line для ratatui.
            .map(|entry| Line::from(entry.clone()))
            // Собираем все видимые строки обратно в Vec<Line>.
            .collect()
    };

    // Создаём отдельный виджет под нижнюю половину observability-панели.
    let logs = Paragraph::new(lines).block(
        Block::default()
            // Заголовок рамки явно говорит, что тут именно лог-поток.
            .title(" LOG STREAM ")
            // Включаем полную рамку вокруг панели логов.
            .borders(Borders::ALL)
            // Оставляем тот же rounded-стиль, чтобы панель совпадала с остальным UI.
            .border_type(BorderType::Rounded)
            // SECONDARY теперь используется осмысленно: он отделяет log-pane от telemetry-pane.
            .border_style(Style::default().fg(theme::SECONDARY))
            // Внутренний padding делает строки лога читаемее.
            .padding(Padding::new(1, 1, 1, 1)),
    );

    // Рисуем журнал в нижней половине средней колонки.
    frame.render_widget(logs, area);
}

// Нижняя строка-подсказка по клавишам.
/// Назначение: вывести подсказки по клавишам и состоянию режима добавления.
fn render_footer(frame: &mut Frame, area: Rect, app: &App) {
    let text = if app.awaiting_callback_address() {
        // В W-режиме подсказка по hex-вводу.
        let current = if app.callback_hex_input.is_empty() {
            "_"
        } else {
            app.callback_hex_input.as_str()
        };
        format!(
            "INJECT MODE | input: {} | hex digits only | Enter injects to header+8 | Backspace edit | Esc cancel",
            current
        )
    } else if app.awaiting_rename() {
        // В режиме переименования показываем текущее редактируемое имя.
        let current = if app.rename_input.is_empty() {
            "_"
        } else {
            app.rename_input.as_str()
        };
        format!(
            "RENAME MODE | input: {} | type new name | Enter confirm | Backspace edit | Esc cancel",
            current
        )
    } else if app.awaiting_device_type() {
        // В режиме добавления показываем текущий ввод.
        let current = if app.device_type_input.is_empty() {
            "_"
        } else {
            app.device_type_input.as_str()
        };
        format!(
            "ADD MODE | input: {} | digits 1-18 | Enter confirm | Backspace edit | Esc cancel",
            current
        )
    } else {
        // В обычном режиме выводим набор горячих клавиш.
        "A add node | R rename target | P pin selected | D free selected | Up/Down navigate | L logger | W inject callback | Q quit"
            .to_owned()
    };

    let footer = Paragraph::new(text).block(
        Block::default()
            .borders(Borders::ALL)
            .border_type(BorderType::Rounded)
            .border_style(Style::default().fg(theme::TEXT_DIM)),
    );

    frame.render_widget(footer, area);
}

/// Назначение: отрисовать декоративную карту города с радарным лучом, сеткой и маркерами активных нод.
fn render_map_city(frame: &mut Frame, area: Rect, app: &App) {
    // Создаём новый canvas-виджет.
    // Canvas нужен, когда мы хотим рисовать линии, точки и геометрические фигуры,
    // а не просто выводить обычный текст.
    let map = Canvas::default()
        // .block(...) прикрепляет к canvas обычную рамку.
        .block(
            // Создаём пустой Block и дальше настраиваем его через цепочку вызовов.
            Block::default()
                // .title(...) пишет заголовок сверху рамки.
                .title(" [ NODE MAP ] ")
                // .borders(Borders::ALL) включает все четыре стороны рамки.
                .borders(Borders::ALL)
                // .border_type(...) меняет форму рамки.
                .border_type(BorderType::Rounded)
                // .border_style(...) задаёт цвет рамки.
                .border_style(Style::default().fg(theme::TEXT_BRIGHT)),
        )
        // .marker(...) задаёт символ, которым canvas будет рисовать точки.
        .marker(Marker::Braille)
        // .x_bounds(...) задаёт видимую область по оси X.
        .x_bounds([-100.0, 100.0])
        // .y_bounds(...) задаёт видимую область по оси Y.
        .y_bounds([-100.0, 100.0])
        // .paint(...) открывает callback, где мы рисуем содержимое карты.
        .paint(|ctx| {
            // Начинаем рисовать фоновую сетку.
            for i in (-100..=100).step_by(20) {
                // Вертикальная линия сетки.
                ctx.draw(&canLine {
                    // x1,y1 = начальная точка линии.
                    x1: i as f64,
                    y1: -100.0,
                    // x2,y2 = конечная точка линии.
                    x2: i as f64,
                    y2: 100.0,
                    // color = цвет этой линии.
                    color: Color::Rgb(20, 20, 20),
                });
                // Горизонтальная линия сетки.
                ctx.draw(&canLine {
                    // Начало линии слева.
                    x1: -100.0,
                    y1: i as f64,
                    // Конец линии справа.
                    x2: 100.0,
                    y2: i as f64,
                    // Цвет совпадает с вертикальными линиями, чтобы сетка выглядела цельно.
                    color: Color::Rgb(20, 20, 20),
                });
            }

            // Описываем несколько прямоугольников, которые имитируют кварталы или здания.
            let buildings = [
                (-78.0, 28.0, 18.0, 16.0),
                (-32.0, 46.0, 22.0, 12.0),
                (18.0, 24.0, 28.0, 18.0),
                (-60.0, -24.0, 20.0, 24.0),
                (12.0, -42.0, 16.0, 18.0),
                (48.0, -10.0, 24.0, 14.0),
            ];
            // Проходим по каждому зданию.
            for (x, y, w, h) in buildings {
                // Рисуем прямоугольник на карте.
                ctx.draw(&Rectangle {
                    // x и y = левый нижний угол прямоугольника.
                    x,
                    y,
                    // width и height = размер прямоугольника.
                    width: w,
                    height: h,
                    // Цвет зданий делаем тусклым, чтобы они не спорили с нодами.
                    color: Color::Rgb(60, 60, 60),
                });
            }

            // Вычисляем фазу пульсации для колец вокруг центра.
            let pulse_phase = app.radar_angle * 25.0;
            // Рисуем три кольца с разным сдвигом, чтобы получился эффект сканирования.
            for offset in [0.0, 30.0, 60.0] {
                // radius = текущий радиус кольца.
                let radius = (pulse_phase + offset) % 100.0;
                // Маленькие кольца пропускаем, чтобы не было визуального мусора в центре.
                if radius > 2.0 {
                    // Circle рисует окружность на canvas.
                    ctx.draw(&Circle {
                        // Центр окружности совпадает с центром карты.
                        x: 0.0,
                        y: 0.0,
                        // radius задаёт размер окружности.
                        radius,
                        // Cyan делает кольца заметными на тёмной сетке.
                        color: Color::Cyan,
                    });
                }
            }

            // Считаем конец радарного луча через cos и sin от текущего угла.
            let end_x = 100.0 * app.radar_angle.cos();
            let end_y = 100.0 * app.radar_angle.sin();
            // Рисуем сам луч как линию из центра наружу.
            ctx.draw(&canLine {
                x1: 0.0,
                y1: 0.0,
                x2: end_x,
                y2: end_y,
                color: Color::Green,
            });

            // Обходим все активные устройства и рисуем каждое на карте.
            for (index, device) in app.active_devices.iter().enumerate() {
                // Координаты генерируются детерминированно из id, чтобы нода всегда была в одной точке.
                let x = ((device.id * 37) % 160) as f64 - 80.0;
                let y = ((device.id * 53) % 160) as f64 - 80.0;

                // blink даёт мигание для выбранной ноды.
                let blink = (app.radar_angle * 10.0).sin() > 0.0;
                // Проверяем, совпадает ли индекс этой ноды с текущим выделением списка.
                let is_selected = app.list_state.selected() == Some(index);
                // Выбираем цвет точки в зависимости от состояния.
                let color = if app.is_pinned_ptr(device.ptr) {
                    // Pinned нода красная.
                    Color::Red
                } else if is_selected && blink {
                    // Выбранная нода периодически мигает белым.
                    Color::White
                } else {
                    // Обычные ноды рисуем бирюзовыми.
                    Color::Rgb(0, 150, 150)
                };

                // Рисуем саму ноду как точку.
                ctx.draw(&Points {
                    coords: &[(x, y)],
                    color,
                });

                // Если нода выбрана, дополнительно соединяем её линией с центром и подписываем.
                if is_selected {
                    ctx.draw(&canLine {
                        x1: 0.0,
                        y1: 0.0,
                        x2: x,
                        y2: y,
                        color: Color::DarkGray,
                    });
                    // print(...) выводит короткую подпись прямо на canvas.
                    ctx.print(x + 3.0, y + 2.0, format!("NODE_{:02}", device.id));
                }
            }

            // Если pinned-узел уже удалён, но всё ещё сохранён в pinned_device,
            // отдельно мигаем крестом в его точке. Это подчёркивает dangling pointer сценарий.
            if let Some(device) = &app.pinned_device {
                let x = ((device.id * 37) % 160) as f64 - 80.0;
                let y = ((device.id * 53) % 160) as f64 - 80.0;
                if !app.pinned_is_active() && (app.radar_angle * 10.0).sin() > 0.0 {
                    ctx.draw(&Points {
                        coords: &[
                            (x, y),
                            (x + 1.0, y),
                            (x - 1.0, y),
                            (x, y + 1.0),
                            (x, y - 1.0),
                        ],
                        color: Color::Red,
                    });
                }
            }
        });

    // Помещаем уже собранный canvas в область area на экране.
    frame.render_widget(map, area);
}

// Преобразуем сырые байты в строки вида:
// 0000: AA BB CC DD ...
/// Назначение: преобразовать сырые байты памяти в читаемый hex dump по строкам.
fn format_hex_dump(bytes: &[u8]) -> Vec<Line<'static>> {
    bytes
        // chunks(8) делит массив байт на куски по 8 байт.
        .chunks(8)
        // enumerate() добавляет индекс чанка: 0, 1, 2, ...
        // Он нужен, чтобы напечатать смещение 0000, 0008, 0010 и т.д.
        .enumerate()
        .map(|(index, chunk)| {
            let rendered = chunk
                .iter()
                // iter() идёт по байтам внутри чанка.
                .map(|byte| format!("{:02X}", byte))
                // Этот map превращает каждый байт в строку hex вида "AF".
                .collect::<Vec<_>>()
                // collect::<Vec<_>>() собирает все hex-строки в вектор.
                .join(" ");
            // join(" ") склеивает их в одну строку через пробел.
            Line::from(format!("{:04X}: {}", index * 8, rendered))
        })
        .collect()
    // Финальный collect() собирает все строки hex dump в Vec<Line>.
}
