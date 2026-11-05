// SPDX-License-Identifier: GPL-3.0-or-later

// Импортируем тип конфигурации framebuffer-а и общий trait framebuffer backend-а.
use super::{Framebuffer, FramebufferConfig, RGB565};

// Описываем headless framebuffer backend, который хранит пиксели только в памяти без GUI-окон.
pub struct Null {
    // Храним исходную конфигурацию framebuffer-а, чтобы внешние устройства знали его размеры и имя.
    pub config: FramebufferConfig,
    // Храним сырые пиксели в RGB565, чтобы display/touchscreen могли работать как и раньше.
    pub framebuffer: Vec<RGB565>,
}

impl Null {
    // Создаем новый headless framebuffer по конфигурации из YAML.
    pub fn new(config: FramebufferConfig) -> Self {
        // Выделяем вектор нужного размера под все пиксели поверхности.
        let mut framebuffer = vec![];
        // Заполняем буфер нулями так, чтобы его длина совпадала с `width * height`.
        framebuffer.resize(config.width as usize * config.height as usize, Default::default());
        // Возвращаем готовый headless framebuffer без каких-либо внешних ресурсов.
        Self { config, framebuffer }
    }
}

// Реализуем общий framebuffer trait для headless backend-а.
impl<Color> Framebuffer<Color> for Null {
    // Возвращаем ссылку на исходную конфигурацию framebuffer-а.
    fn get_config(&self) -> &FramebufferConfig {
        // Просто отдаем сохраненную конфигурацию без преобразований.
        &self.config
    }

    // Возвращаем mutable view на внутренний пиксельный буфер.
    fn get_pixels(&mut self) -> &mut [Color] {
        // Переинтерпретируем внутренний буфер RGB565 как срез нужного цветового типа.
        unsafe {
            std::slice::from_raw_parts_mut(
                self.framebuffer.as_mut_ptr() as *mut Color,
                self.framebuffer.len() * std::mem::size_of::<RGB565>() / std::mem::size_of::<Color>(),
            )
        }
    }
}
