// Указываем лицензию файла, чтобы было понятно, под какой лицензией распространяется этот исходник.
// SPDX-License-Identifier: GPL-3.0-or-later

// Импортируем derive Deserialize, чтобы структуры можно было заполнять из YAML.
use serde::Deserialize;

// Просим автоматически генерировать Debug и Deserialize для структуры Region.
#[derive(Debug, Deserialize)]
// Описываем один memory region из YAML-конфига.
pub struct Region {
   // Имя региона, полезное для логов и диагностических сообщений.
   pub name: String,
   // Базовый адрес региона в memory map.
   pub start: u32,
   // Размер региона в байтах.
   pub size: u32,
   // Опциональный путь к файлу, который нужно загрузить в этот регион.
   pub load: Option<String>,
}

// Просим автоматически генерировать Debug и Deserialize для структуры Patch.
#[derive(Debug, Deserialize)]
// Описываем один бинарный патч, который будет записан в память после загрузки регионов.
pub struct Patch {
   // Адрес начала патча.
   pub start: u32,
   // Последовательность байтов, которую нужно записать в память.
   pub data: Vec<u8>,
}

// Просим автоматически генерировать Debug и Deserialize для структуры Cpu.
#[derive(Debug, Deserialize)]
// Описываем CPU-секцию YAML-конфига.
pub struct Cpu {
    // Путь к SVD-файлу, описывающему карту периферии устройства.
    pub svd: String,
    // Адрес таблицы векторов, с которой начнется чтение SP и reset handler.
    pub vector_table: u32,
}

// Просим автоматически генерировать Debug и Deserialize для корневой структуры Config.
#[derive(Debug, Deserialize)]
// Описываем полный YAML-конфиг эмулятора.
pub struct Config {
   // Вкладываем CPU-секцию.
   pub cpu: Cpu,
   // Храним список memory region-ов, которые нужно отобразить в память Unicorn.
   pub regions: Vec<Region>,
   // Храним опциональный список бинарных патчей.
   pub patches: Option<Vec<Patch>>,
   // Храним опциональную конфигурацию внутренних периферий.
   pub peripherals: Option<crate::peripherals::PeripheralsConfig>,
   // Храним опциональную конфигурацию внешних устройств, подключенных к периферии.
   pub devices: Option<crate::ext_devices::ExtDevicesConfig>,
   // Храним опциональную конфигурацию framebuffer-ов.
   pub framebuffers: Option<Vec<crate::framebuffers::FramebufferConfig>>,
}
