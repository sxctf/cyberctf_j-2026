// Указываем лицензию файла, чтобы было понятно, на каких условиях распространяется исходник.
// SPDX-License-Identifier: GPL-3.0-or-later

// Подключаем модуль с типами конфигурации YAML-файла.
mod config;
// Подключаем модуль, в котором находится основной цикл исполнения эмулятора.
mod emulator;
// Подключаем модуль с утилитами чтения файлов и обработки ошибок Unicorn.
mod util;
// Подключаем модуль реализации внутренних периферий STM32.
mod peripherals;
// Подключаем модуль внешних устройств, навешиваемых на периферию.
mod ext_devices;
// Подключаем модуль подготовки системы и memory map.
mod system;
// Подключаем модуль framebuffer-ов для дисплеев и окон SDL.
mod framebuffers;

// Импортируем prelude для записи форматированного текста в лог-буфер env_logger.
use std::io::prelude::*;
// Импортируем BufRead, чтобы в фоне читать строки со stdin и отправлять их в UART queue.
use std::io::BufRead;
// Импортируем переменные окружения, чтобы включать специальный bridge-режим через env flag.
use std::env;
// Импортируем очередь FIFO, потому что control-команды удобно передавать между потоками именно так.
use std::collections::VecDeque;
// Импортируем Mutex и OnceLock, чтобы завести глобальную потокобезопасную очередь control-команд.
use std::sync::{Mutex, OnceLock};
// Импортируем relaxed ordering для чтения атомиков статистики исполнения.
use std::sync::atomic::Ordering::Relaxed;
// Импортируем thread, чтобы запустить фоновый stdin-reader для headless bridge режима.
use std::thread;
// Импортируем derive/API из clap для разбора аргументов командной строки.
use clap::Parser;
// Импортируем anyhow::Result и Context для удобной обработки ошибок с пояснениями.
use anyhow::{Result, Context};
// Импортируем стиль записи env_logger, чтобы управлять цветным выводом.
use env_logger::fmt::WriteStyle;
// Импортируем уровни логирования.
use log::LevelFilter;

// Импортируем тип Config из локального модуля config.
use config::Config;
// Импортируем helper отправки строк из host stdin в UART probe.
use ext_devices::usart_probe::push_host_line;
// Импортируем главный entrypoint эмуляции.
use emulator::run_emulator;
// Импортируем helper чтения текстовых файлов целиком.
use util::read_file_str;


// Подключаем logging-макросы `info!`, `debug!`, `trace!` и т.д. как `extern crate log`.
#[macro_use]
// Объявляем зависимость `log`, чтобы макросы были доступны во всем crate.
extern crate log;

// Описываем набор служебных команд, которыми bridge управляет эмулятором в headless-режиме.
#[derive(Debug, Clone)]
pub enum HostControlCommand {
    // Команда запросить свежий snapshot без продвижения исполнения.
    Status,
    // Команда выполнить ограниченное число инструкций.
    Step(u64),
    // Команда считать память по адресу и длине.
    Dump(u32, usize),
    // Команда передать строку во входящий UART прошивки.
    Uart(String),
    // Команда принудительно выставить состояние внешнего входного пина.
    PinSet(String, bool),
    // Команда вывести полный набор ARM core registers.
    Regs,
    // Команда аккуратно завершить процесс без внешнего kill.
    Quit,
}

// Заводим глобальную очередь control-команд, потому что stdin-reader и эмулятор работают в разных потоках.
static HOST_CONTROL_QUEUE: OnceLock<Mutex<VecDeque<HostControlCommand>>> = OnceLock::new();

// Возвращаем глобальную очередь control-команд, создавая ее лениво при первом обращении.
fn host_control_queue() -> &'static Mutex<VecDeque<HostControlCommand>> {
    // Ленивая инициализация позволяет не трогать очередь, если bridge-режим вообще не включался.
    HOST_CONTROL_QUEUE.get_or_init(|| Mutex::new(VecDeque::new()))
}

// Проверяем, включен ли специальный bridge-режим через переменную окружения.
pub fn bridge_mode_enabled() -> bool {
    // Считаем режим включенным только при явном значении `1`, чтобы поведение было предсказуемым.
    env::var("STM32_EMULATOR_BRIDGE_MODE").ok().as_deref() == Some("1")
}

// Кладем новую control-команду в глобальную очередь для дальнейшей обработки в эмуляторе.
fn push_control_command(command: HostControlCommand) {
    // Если mutex успешно захвачен, добавляем команду в хвост FIFO-очереди.
    if let Ok(mut guard) = host_control_queue().lock() {
        guard.push_back(command);
    }
}

// Пытаемся достать следующую control-команду без блокировки основного потока эмуляции.
pub fn pop_control_command() -> Option<HostControlCommand> {
    // Если mutex захвачен успешно, вынимаем самый старый элемент очереди.
    host_control_queue()
        .lock()
        .ok()
        .and_then(|mut guard| guard.pop_front())
}

// Разбираем беззнаковое число из строки, поддерживая и `0x`, и обычный десятичный формат.
fn parse_u32_token(value: &str) -> Option<u32> {
    // Если значение начинается с `0x`, парсим его как шестнадцатеричное.
    if let Some(hex) = value.strip_prefix("0x").or_else(|| value.strip_prefix("0X")) {
        u32::from_str_radix(hex, 16).ok()
    } else {
        // Иначе пытаемся прочитать строку как обычное десятичное число.
        value.parse::<u32>().ok()
    }
}

// Разбираем строку служебной control-команды, пришедшей от bridge, в наш enum.
fn parse_control_line(line: &str) -> Option<HostControlCommand> {
    // Убираем пробелы по краям, чтобы разбор был устойчив к случайным отступам.
    let trimmed = line.trim();
    // Полностью пустую строку считаем отсутствием команды.
    if trimmed.is_empty() {
        return None;
    }
    // Команда `status` не имеет аргументов и просто просит актуальный snapshot.
    if trimmed == "status" {
        return Some(HostControlCommand::Status);
    }
    // Команда `quit` просит процесс завершиться без внешнего сигнала.
    if trimmed == "quit" {
        return Some(HostControlCommand::Quit);
    }
    // Команда `uart <text>` прокидывает пользовательский текст во входящий UART прошивки.
    if let Some(rest) = trimmed.strip_prefix("uart ") {
        return Some(HostControlCommand::Uart(rest.to_string()));
    }
    // Команда `regs` просит напечатать полный набор регистров ядра.
    if trimmed == "regs" {
        return Some(HostControlCommand::Regs);
    }
    // Команда `pin set <name> <0|1>` управляет внешним логическим уровнем входного пина.
    if let Some(rest) = trimmed.strip_prefix("pin set ") {
        // Разбиваем остаток строки на имя пина и значение уровня.
        let mut parts = rest.split_whitespace();
        // Пытаемся прочитать имя пина.
        let pin_name = parts.next()?.to_string();
        // Пытаемся прочитать значение уровня.
        let raw_level = parts.next()?;
        // Преобразуем текст уровня в boolean.
        let level = match raw_level {
            "0" | "low" | "LOW" => false,
            "1" | "high" | "HIGH" => true,
            _ => return None,
        };
        // Возвращаем собранную control-команду.
        return Some(HostControlCommand::PinSet(pin_name, level));
    }
    // Команда `step <n>` просит выполнить ровно ограниченный бюджет инструкций.
    if let Some(rest) = trimmed.strip_prefix("step ") {
        return rest.trim().parse::<u64>().ok().map(HostControlCommand::Step);
    }
    // Команда `dump <addr> <len>` просит вернуть дамп памяти по адресу и длине.
    if let Some(rest) = trimmed.strip_prefix("dump ") {
        // Разбиваем остаток строки на токены адреса и длины.
        let mut parts = rest.split_whitespace();
        // Пытаемся прочитать адрес.
        let addr = parts.next().and_then(parse_u32_token)?;
        // Пытаемся прочитать длину.
        let len = parts.next()?.parse::<usize>().ok()?;
        // Возвращаем собранную control-команду.
        return Some(HostControlCommand::Dump(addr, len));
    }
    // Все остальные строки считаем неизвестными служебными командами.
    None
}

/// Краткое описание программы для CLI help, которое читает clap derive.
/// STM32 Emulator
// Просим clap автоматически сгенерировать parser для структуры Args.
#[derive(Parser, Debug)]
// Описываем все аргументы командной строки этого бинаря.
pub struct Args {
    /// Комментарий для clap help: путь к конфигурационному YAML-файлу.
    /// Config file
    // Позиционный аргумент с путем к config.yaml.
    config: String,

    /// Комментарий для clap help: уровень verbosity, флаг можно повторять.
    /// Verbosity. Can be repeated. -vvvv is the maximum.
    // Короткий и длинный флаг verbosity, считающий количество повторений.
    #[clap(short, long, parse(from_occurrences))]
    // Число повторений флага `-v`.
    verbose: u8,

    /// Комментарий для clap help: ограничение по числу инструкций.
    /// Maximum number of instructions to execute
    // Короткий и длинный флаг для ограничения числа исполняемых инструкций.
    #[clap(short, long)]
    // Опциональный лимит инструкций.
    max_instructions: Option<u64>,

    /// Комментарий для clap help: остановка по достижении адреса PC.
    /// Stop emulation when pc reaches this address
    // Короткий и длинный флаг, который умеет парсить hex или decimal адрес.
    #[clap(short, long, parse(try_from_str=clap_num::maybe_hex))]
    // Опциональный адрес остановки по PC.
    stop_addr: Option<u32>,

    /// Комментарий для clap help: остановка при обнаружении busy loop.
    /// Stop emulation when the program reaches a busy loop
    // Короткий и длинный булев флаг busy-loop детектора.
    #[clap(short, long)]
    // Флаг включения остановки на busy loop.
    busy_loop_stop: bool,

    /// Комментарий для clap help: управление цветным выводом.
    /// Colorize output
    // Короткий и длинный флаг выбора режима цветного вывода.
    #[clap(short, long, arg_enum, default_value="auto")]
    // Перечисление режима цветного вывода.
    color: Color,

    /// Комментарий для clap help: частота обработки pending interrupts.
    /// Run pending interrupts every N instructions
    /// Пояснение, что меньшее значение корректнее, но медленнее.
    /// Shorter is more correct, but is slower.
    // Короткий и длинный флаг периода обработки pending interrupts.
    #[clap(short, long, default_value="1")]
    // Число инструкций между проходами по pending interrupts.
    interrupt_period: u32,

    /// Комментарий для clap help: дамп стека в конце исполнения.
    /// Dump stack at the end. Parameter is the number of words to print
    // Короткий и длинный флаг для включения дампа стека.
    #[clap(short, long)]
    // Число слов стека, которое нужно вывести.
    dump_stack: Option<usize>,
}

// Просим clap трактовать enum как CLI-аргумент перечислимого типа.
#[derive(clap::ArgEnum, Clone, Copy, Debug)]
// Описываем режимы выбора цветного вывода.
enum Color {
    // Автоматически решать, нужен ли цвет.
    Auto,
    // Всегда включать цвет.
    Always,
    // Никогда не использовать цвет.
    Never,
}

// Реализуем преобразование нашего Color enum в тип WriteStyle, который понимает env_logger.
impl std::convert::From<Color> for WriteStyle {
    // Описываем, как конвертировать Color в WriteStyle.
    fn from(c: Color) -> Self {
        // Выбираем стиль логгера по значению enum.
        match c {
            // Принудительно включаем цвет.
            Color::Always => WriteStyle::Always,
            // Принудительно выключаем цвет.
            Color::Never => WriteStyle::Never,
            // Доверяем автоопределению.
            Color::Auto => WriteStyle::Auto,
        }
    }
}

// Заводим глобальную mutable переменную verbosity.
static mut VERBOSE: u8 = 0;

// Возвращаем глобальное значение verbosity из любого места crate.
pub fn verbose() -> u8 {
    // Читаем глобальное mutable значение через unsafe.
    unsafe { VERBOSE }
}

// Инициализируем logging subsystem по аргументам CLI.
fn init_logging(args: &Args) {
    // Сохраняем verbosity в глобальную переменную, чтобы другие модули могли ее читать.
    unsafe { VERBOSE = args.verbose };

    // Выбираем базовый уровень логирования по числу `-v`.
    let lf = match args.verbose {
        // Без `-v` показываем только info и выше.
        0 => LevelFilter::Info,
        // С одним `-v` показываем debug и выше.
        1 => LevelFilter::Debug,
        // С двумя и более `-v` показываем trace и выше.
        _ => LevelFilter::Trace,
    };

    // Заводим mutable глобал для последнего числа инструкций, если понадобится вычислять delta.
    static mut LAST_NUM_INSTRUCTIONS: u64 = 0;

    // Создаем builder env_logger.
    env_logger::Builder::new()
        // Устанавливаем выбранный уровень логирования.
        .filter_level(lf)
        // Устанавливаем режим цветного вывода.
        .write_style(args.color.into())
        // Явно направляем вывод логов в stdout.
        .target(env_logger::Target::Stdout)
        // Переопределяем формат каждой строки лога.
        .format(|buf, record| {
            // Импортируем enum цветов env_logger внутри callback-а форматирования.
            use env_logger::fmt::Color;
            // Читаем атомик общего числа исполненных инструкций.
            let num_instructions = emulator::NUM_INSTRUCTIONS.load(Relaxed);
            // Потенциальный расчет delta закомментирован автором как неиспользуемый.
            //let delta_instructions = num_instructions - unsafe { LAST_NUM_INSTRUCTIONS };
            // Сохраняем текущее число инструкций как последнее.
            unsafe { LAST_NUM_INSTRUCTIONS = num_instructions };
            // Читаем адрес последней выполненной инструкции.
            let pc = unsafe { emulator::LAST_INSTRUCTION.0 };

            // Берем style builder у лог-буфера.
            let mut style = buf.style();
            // Форматируем текст уровня лога с цветом по severity.
            let level = match record.level() {
                // Красим ERROR в красный.
                log::Level::Error => style.set_color(Color::Red).set_intense(true).value("ERROR"),
                // Красим WARN в желтый.
                log::Level::Warn =>  style.set_color(Color::Yellow).set_intense(true).value("WARN "),
                // Красим INFO в зеленый.
                log::Level::Info =>  style.set_color(Color::Green).set_intense(true).value("INFO "),
                // Красим DEBUG в голубой.
                log::Level::Debug => style.set_color(Color::Cyan).set_intense(true).value("DEBUG"),
                // Красим TRACE в синий.
                log::Level::Trace => style.set_color(Color::Blue).set_intense(true).value("TRACE"),
            };

            // Берем новый style builder для заголовка строки.
            let mut style = buf.style();
            // Красим заголовок в интенсивный черный/серый.
            style.set_color(Color::Black).set_intense(true);
            // Старая форма заголовка с delta закомментирована автором.
            //let header = format!("[tsc={:08} dtsc=+{:08} pc=0x{:08x}]", num_instructions, delta_instructions, pc);
            // Формируем компактный заголовок с числом инструкций и PC.
            let header = format!("[clk={:08} pc=0x{:08x}]", num_instructions, pc);
            // Оборачиваем строку заголовка в цветной styled value.
            let header = style.value(header);

            // Пишем итоговую строку лога в буфер.
            writeln!(buf, "{} {} {}", header, level, record.args())
        })
        // Финализируем и активируем глобальный logger.
        .init();
}

// Главная функция программы.
fn main() -> Result<()> {
    // Если bridge-режим включен, поднимаем фоновый reader stdin для control-команд и UART-ввода.
    if bridge_mode_enabled() {
        // Выделяем отдельный поток, чтобы ожидание stdin не блокировало основной цикл эмуляции.
        thread::spawn(|| {
            // Получаем handle стандартного ввода процесса.
            let stdin = std::io::stdin();
            // Читаем stdin построчно, потому что bridge общается line-oriented протоколом.
            for line in stdin.lock().lines() {
                // Обрабатываем только успешно прочитанные строки.
                if let Ok(line) = line {
                    // Убираем пробелы по краям для устойчивого разбора.
                    let trimmed = line.trim();
                    // Полностью пустые строки сразу пропускаем.
                    if trimmed.is_empty() {
                        continue;
                    }
                    // Строки с префиксом `:bridge ` считаем служебным control-протоколом.
                    if let Some(rest) = trimmed.strip_prefix(":bridge ") {
                        // Если команда успешно распозналась, кладем ее в очередь для главного цикла.
                        if let Some(command) = parse_control_line(rest) {
                            push_control_command(command);
                        }
                    } else {
                        // Все прочие строки трактуем как обычный host->UART текст.
                        push_host_line(trimmed);
                    }
                }
            }
        });
    }

    // Разбираем аргументы командной строки через clap derive parser.
    let args = Args::parse();
    // Инициализируем logging на основе разобранных аргументов.
    init_logging(&args);

    // Читаем YAML-конфиг как строку и парсим его в структуру Config.
    let config: Config = serde_yaml::from_str(&read_file_str(&args.config)?)
        // При ошибке парсинга добавляем путь к проблемному файлу.
        .with_context(|| format!("Failed to parse {}", args.config))?;

    // Читаем SVD-файл, указанный в конфиге, и парсим его в структуру устройства.
    let device = svd_parser::parse(&read_file_str(&config.cpu.svd)?)
        // При ошибке парсинга добавляем путь к проблемному SVD-файлу.
        .with_context(|| format!("Failed to parse {}", config.cpu.svd))?;

    // Передаем конфиг, SVD-описание устройства и CLI-аргументы в главный цикл эмулятора.
    run_emulator(config, device, args)
}
