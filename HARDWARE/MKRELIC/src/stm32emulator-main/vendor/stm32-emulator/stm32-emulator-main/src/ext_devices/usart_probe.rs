// SPDX-License-Identifier: GPL-3.0-or-later

// Импортируем anyhow::Result, потому что конструктор устройства возвращает fallible API.
use anyhow::Result;
// Импортируем Deserialize, чтобы можно было прочитать конфиг usart_probe из YAML.
use serde::Deserialize;
// Импортируем VecDeque, потому что host UART RX удобно моделировать FIFO-очередью байтов.
use std::collections::VecDeque;
// Импортируем Mutex и OnceLock, чтобы сделать глобальную потокобезопасную очередь host->firmware.
use std::sync::{Mutex, OnceLock};

// Импортируем агрегат System, который доступен внешним устройствам при чтении/записи.
use crate::system::System;

// Импортируем trait ExtDevice, который реализуют все внешние устройства upstream-эмулятора.
use super::ExtDevice;

// Заводим глобальную очередь host UART RX, потому что bridge кладет байты в нее из другого контекста исполнения.
static HOST_UART_RX: OnceLock<Mutex<VecDeque<u8>>> = OnceLock::new();

// Возвращаем глобальную очередь host UART RX, создавая ее лениво при первом обращении.
fn host_uart_rx() -> &'static Mutex<VecDeque<u8>> {
    // Ленивая инициализация позволяет вообще не создавать очередь, если usart_probe не используется.
    HOST_UART_RX.get_or_init(|| Mutex::new(VecDeque::new()))
}

// Кладем целую строку от host-side bridge в UART RX очередь прошивки.
pub fn push_host_line(line: &str) {
    // Если mutex захвачен успешно, побайтно записываем строку в FIFO.
    if let Ok(mut guard) = host_uart_rx().lock() {
        // Каждый байт исходной строки передаем в очередь отдельно, потому что периферия читает UART по байтам.
        for byte in line.as_bytes() {
            guard.push_back(*byte);
        }
        // После payload добавляем перевод строки, чтобы firmware могла обрабатывать line-oriented протокол.
        guard.push_back(b'\n');
    }
}

// Просим автоматически генерировать Debug, Deserialize и Default для конфигурации usart_probe.
#[derive(Debug, Deserialize, Default)]
// Описываем минимальный YAML-конфиг usart_probe.
pub struct UsartProbeConfig {
    // Храним имя периферии, к которой нужно подключить probe, например `USART1`.
    pub peripheral: String,
}

// Просим автоматически генерировать Default для runtime-состояния usart_probe.
#[derive(Default)]
// Описываем внешнее устройство, которое связывает host input и UART прошивки.
pub struct UsartProbe {
    // Храним исходный конфиг устройства.
    pub config: UsartProbeConfig,
    // Храним человекочитаемое имя, удобное для логов.
    name: String,
    // Храним буфер текущей TX-строки, пока прошивка не отправит символ конца строки.
    rx: Vec<u8>,
}

// Реализуем конструктор usart_probe.
impl UsartProbe {
    // Создаем новый usart_probe из YAML-конфига.
    pub fn new(config: UsartProbeConfig) -> Result<Self> {
        // Возвращаем устройство, сохраняя конфиг и заполняя остальное значениями по умолчанию.
        Ok(Self { config, ..Self::default() })
    }
}

// Реализуем trait внешнего устройства для UART-пробы.
impl ExtDevice<(), u8> for UsartProbe {
    // Подключаем устройство к конкретной внутренней периферии и возвращаем имя подключения.
    fn connect_peripheral(&mut self, peri_name: &str) -> String {
        // Формируем человекочитаемое имя вида `USART1 usart-probe`.
        self.name = format!("{} usart-probe", peri_name);
        // Возвращаем это имя вызывающему коду.
        self.name.clone()
    }

    // Сообщаем, есть ли у host-side еще байты для чтения прошивкой.
    fn has_data(&self) -> bool {
        // Если очередь удалось открыть, проверяем, не пуста ли она.
        host_uart_rx()
            .lock()
            .map(|guard| !guard.is_empty())
            .unwrap_or(false)
    }

    // Отдаем прошивке следующий байт из host-side RX очереди.
    fn read(&mut self, _sys: &System, _addr: ()) -> u8 {
        // Если очередь доступна, снимаем один байт из головы FIFO, иначе отдаем ноль по умолчанию.
        host_uart_rx()
            .lock()
            .ok()
            .and_then(|mut guard| guard.pop_front())
            .unwrap_or_default()
    }

    // Принимаем один байт, который прошивка отправила наружу через UART TX.
    fn write(&mut self, _sys: &System, _addr: (), v: u8) {
        // Если байт равен LF, считаем, что прошивка завершила строку.
        if v == 0x0a {
            // Комментарий автора upstream: это конец строки.
            let line = String::from_utf8_lossy(&self.rx);
            // Обрезаем пробелы и перевод строки по краям.
            let line = line.trim();
            // Пишем строку в обычный лог upstream.
            info!("{} '{}'", self.name, line);
            // Печатаем специальный machine-readable маркер для нашего bridge runtime.
            println!("UART_TX:{}", line);
            // Очищаем буфер текущей строки.
            self.rx.clear();
        } else {
            // Иначе продолжаем накапливать байты до конца строки.
            self.rx.push(v);
        }
    }
}
