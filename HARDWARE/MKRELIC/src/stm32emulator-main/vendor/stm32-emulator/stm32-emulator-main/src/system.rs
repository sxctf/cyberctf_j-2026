// Указываем лицензию файла, чтобы было ясно, на каких условиях распространяется код.
// SPDX-License-Identifier: GPL-3.0-or-later

// Импортируем Rc для совместного владения объектами периферии и внешних устройств.
// Импортируем RefCell для внутренней мутабельности и передачи Unicorn в callback-и.
use std::{rc::Rc, cell::RefCell};
// Импортируем основной тип Unicorn и enum разрешений памяти.
use unicorn_engine::{Unicorn, unicorn_const::Permission};
// Импортируем внутренние периферии, GPIO-порты, внешние устройства, утилиты, конфиг и framebuffer-ы.
use crate::{peripherals::{Peripherals, gpio::GpioPorts}, ext_devices::ExtDevices, util::{UniErr, round_up, self}, config::Config, framebuffers::Framebuffers};
// Импортируем anyhow::Result и Context для ошибок с пояснениями.
use anyhow::{Context as _, Result};
// Импортируем тип SVD-описания устройства.
use svd_parser::svd::Device as SvdDevice;

// Авторский комментарий: System передается в read/write hooks, так удобнее, чем тащить все по отдельности.
// System is passed around during read/write hooks. It's more convenient than passing each thing individually.
// Автор иронизирует, что можно было бы сделать это глобальной переменной.
// Maybe it should just be a global variable, and we call it a day.
// Описываем агрегат System, который связывает Unicorn, периферию и внешние устройства.
pub struct System<'a, 'b> {
    // Автор отмечает, что не до конца доволен использованием RefCell здесь.
    // not sure how to not have a refcell here
    // Храним mutable ссылку на Unicorn внутри RefCell, чтобы callbacks могли брать ее mutably во время исполнения.
    pub uc: RefCell<&'a mut Unicorn<'b, ()>>,
    // Автор извиняется за короткие имена полей, но считает полные имена слишком многословными.
    // Sorry for the single letter variables, it just gets too verbose at times.
    // Храним Rc-обертку над набором периферий STM32.
    pub p: Rc<Peripherals>,
    // Храним Rc-обертку над набором внешних устройств, подключенных к периферии.
    pub d: Rc<ExtDevices>,
}

// Реализуем методы для агрегата System.
impl<'a, 'b> System<'a, 'b> {
    // Создаем новый System из Unicorn, Peripherals и ExtDevices.
    fn new(uc: &'a mut Unicorn<'b, ()>, p: Peripherals,  d: ExtDevices) -> Self {
        // Возвращаем структуру с упакованными полями.
        Self {
            // Заворачиваем mutable ссылку на Unicorn в RefCell.
            uc: RefCell::new(uc),
            // Заворачиваем Peripherals в Rc для совместного использования в callback-ах.
            p: Rc::new(p),
            // Заворачиваем ExtDevices в Rc для совместного использования в callback-ах.
            d: Rc::new(d),
        }
    }

    // Навешиваем все memory-mapped периферии на Unicorn через mmio callbacks.
    fn bind_peripherals_to_unicorn(&mut self) -> Result<()> {
        // Идем по всем известным диапазонам адресов периферии.
        for (start, end) in Peripherals::MEMORY_MAPS {
            // Создаем callback чтения для конкретного диапазона.
            let read_cb = {
                // Клонируем Rc на периферию для захвата в closure.
                let p = self.p.clone();
                // Клонируем Rc на внешние устройства для захвата в closure.
                let d = self.d.clone();
                // Возвращаем closure чтения MMIO.
                move |uc: &mut Unicorn<'_, ()>, addr, size| {
                    // На время вызова собираем временный System вокруг текущего Unicorn instance и Rc-объектов.
                    let mut sys = System { uc: RefCell::new(uc), p: p.clone(), d: d.clone() };
                    // Делегируем чтение в Peripherals::read, добавляя base address региона.
                    p.read(&mut sys, start + addr as u32, size as u8) as u64
                }
            };

            // Создаем callback записи для конкретного диапазона.
            let write_cb = {
                // Клонируем Rc на периферию для захвата в closure.
                let p = self.p.clone();
                // Клонируем Rc на внешние устройства для захвата в closure.
                let d = self.d.clone();
                // Возвращаем closure записи MMIO.
                move |uc: &mut Unicorn<'_, ()>, addr, size, value| {
                    // На время вызова собираем временный System вокруг текущего Unicorn instance и Rc-объектов.
                    let mut sys = System { uc: RefCell::new(uc), p: p.clone(), d: d.clone() };
                    // Делегируем запись в Peripherals::write, добавляя base address региона.
                    p.write(&mut sys, start + addr as u32, size as u8, value as u32)
                }
            };

            // Регистрируем MMIO-диапазон в Unicorn.
            self.uc.borrow_mut().mmio_map(start as u64, (end-start) as usize, Some(read_cb), Some(write_cb))
                // Оборачиваем ошибку Unicorn в локальный тип UniErr.
                .map_err(UniErr)
                // Добавляем контекст ошибки для диагностики.
                .context("Failed to mmio_map()")?;
        }

        // Возвращаем успешное завершение привязки периферий.
        Ok(())
    }
}

// Загружаем memory regions и бинарные патчи из Config в Unicorn memory space.
fn load_memory_regions(uc: &mut Unicorn<()>, config: &Config) -> Result<()> {
    // Идем по всем регионам, описанным в YAML-конфиге.
    for region in &config.regions {
        // Пишем debug-сообщение о том, какой регион сейчас маппим.
        debug!("Mapping region start=0x{:08x} len=0x{:x} name={}",
            region.start, region.size, region.name);

        // Округляем размер региона вверх до границы страницы, как требует API mem_map().
        let size = round_up(region.size as usize, 4096); // magic number is from mem_map() documentation
        // Создаем mapped memory region в Unicorn с полным доступом.
        uc.mem_map(region.start.into(), size, Permission::ALL)
            // Оборачиваем ошибку Unicorn в UniErr.
            .map_err(UniErr)
            // Добавляем пояснение о том, какой регион не удалось отобразить.
            .with_context(||
                format!("Memory mapping of peripheral={} failed", region.name))?;

        // Если у региона есть файл-источник, загружаем его в mapped память.
        if let Some(ref load) = region.load {
            // Пишем info-сообщение о загружаемом файле и базовом адресе.
            info!("Loading file={} at base=0x{:08x}", load, region.start);
            // Читаем файл целиком в память.
            let content = util::read_file(load)?;
            // Ограничиваем длину содержимого размером region-а.
            let content = &content[0..content.len().min(size)];
            // Записываем содержимое в память Unicorn по базовому адресу региона.
            uc.mem_write(region.start.into(), content).map_err(UniErr)?;
        }
    }

    // Идем по списку патчей, если он вообще задан.
    for patch in config.patches.as_ref().unwrap_or(&vec![]) {
        // Записываем байты патча по указанному адресу.
        uc.mem_write(patch.start.into(), &patch.data)
            // Оборачиваем ошибку Unicorn в UniErr.
            .map_err(UniErr)
            // Добавляем контекст ошибки с адресом патча.
            .with_context(||
                format!("Failed to apply patch at addr={}", patch.start))?;
    }

    // Возвращаем успешное завершение загрузки регионов и патчей.
    Ok(())
}

// Готовим всю систему эмуляции до старта CPU execution.
pub fn prepare<'a, 'b>(uc: &'a mut Unicorn<'b, ()>, config: Config, svd_device: SvdDevice)
-> Result<(System<'a, 'b>, Framebuffers)>
  {
    // Сначала создаем regions памяти и заливаем в них firmware/данные/патчи.
    load_memory_regions(uc, &config)?;

    // Создаем framebuffer-ы из конфигурации, либо используем пустой список по умолчанию.
    let framebuffers = Framebuffers::from_config(config.framebuffers.unwrap_or_default());
    // Создаем пустой набор GPIO-портов, который потом будут разделять периферии и внешние устройства.
    let mut gpio: GpioPorts = Default::default();
    // Создаем внешние устройства из config.devices, связывая их с GPIO и framebuffer-ами.
    let ext_devices = config.devices.unwrap_or_default().into_ext_devices(&mut gpio, &framebuffers)?;
    // Создаем внутренние периферии из SVD, конфигурации периферии, GPIO и внешних устройств.
    let peripherals = Peripherals::from_svd(svd_device, config.peripherals.unwrap_or_default(), gpio, &ext_devices);

    // Собираем агрегат System из Unicorn, периферии и внешних устройств.
    let mut system = System::new(uc, peripherals, ext_devices);
    // Навешиваем MMIO callbacks внутренних периферий на Unicorn.
    system.bind_peripherals_to_unicorn()?;
    // Возвращаем готовый System и framebuffer-ы.
    Ok((system, framebuffers))
}
