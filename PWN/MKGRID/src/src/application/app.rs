// std::ffi::CString нужен для передачи строки из Rust в C.
// Обычный Rust String не гарантирует формат, который ожидает C.
use std::{
    // CString хранит строку в C-совместимом виде с завершающим нулём.
    ffi::CString,
    // File нужен, чтобы прочитать содержимое pipe как обычный файловый дескриптор.
    fs::File,
    // Read нужен для метода read_to_end(...), которым мы читаем вывод логгера.
    io::Read,
    // В os::fd лежит FromRawFd для преобразования сырого fd в File.
    os::{
        fd::FromRawFd,
        // c_char и c_void - низкоуровневые C-типы для FFI.
        raw::{c_char, c_void},
    },
    // ptr нужен для ptr::null_mut(), который мы передаём в fflush(NULL).
    ptr,
};

// ListState хранит состояние выделения в списке ratatui.
use ratatui::widgets::ListState;

// Импортируем enum с типами устройств.
use crate::models::{
    ctOS::CtosSession,
    devices::{DeviceEntry, DeviceType},
};

// unsafe extern "C" объявляет функции, которые реализованы в C, а не в Rust.
// unsafe здесь нужен, потому что компилятор не может сам гарантировать безопасность FFI.
unsafe extern "C" {
    // Эта функция создаёт C-сессию и возвращает сырой указатель на память.
    // Назначение: выделить C-сессию устройства и вернуть указатель на неё.
    fn ctos_alloc_session(name: *const c_char, d_type: u16) -> *mut c_void;
    // Эта функция освобождает память, которую раньше выделила C-библиотека.
    // Назначение: освободить память ранее созданной C-сессии.
    fn ctos_free_session(ptr: *mut c_void);
    // Эта функция вызывает callback из C-структуры и печатает его вывод в stdout.
    // Назначение: запустить C-логгер для выбранной сессии.
    fn ctos_logger(ptr: *mut c_void);
    // pipe(...) создаёт пару файловых дескрипторов: read-end и write-end.
    // Назначение: временно перехватить stdout логгера в память, а не прямо в терминал.
    fn pipe(fds: *mut i32) -> i32;
    // dup(...) делает копию файлового дескриптора.
    // Назначение: сохранить оригинальный stdout, чтобы потом вернуть его назад.
    fn dup(fd: i32) -> i32;
    // dup2(...) переназначает один файловый дескриптор на другой.
    // Назначение: временно подменить stdout на pipe.
    fn dup2(oldfd: i32, newfd: i32) -> i32;
    // close(...) закрывает файловый дескриптор.
    // Назначение: не оставлять утечки fd после перехвата логов.
    fn close(fd: i32) -> i32;
    // fflush(NULL) заставляет C stdio сбросить буферы stdout/stderr.
    // Назначение: гарантированно дочитать текст, который напечатал C-логгер.
    fn fflush(stream: *mut c_void) -> i32;
}

// App = всё состояние приложения в одном месте.
pub struct App {
    // Все ещё "живые" устройства, которые не были удалены.
    pub(crate) active_devices: Vec<DeviceEntry>,
    // Состояние курсора в левом списке.
    pub(crate) list_state: ListState,
    // Отдельно храним pinned устройство.
    // Даже если оно потом будет освобождено, копия записи тут останется.
    pub(crate) pinned_device: Option<DeviceEntry>,
    // Строка, которую пользователь вводит в режиме Add Mode.
    pub(crate) device_type_input: String,
    // Строка, которую пользователь редактирует в режиме Rename Mode.
    pub(crate) rename_input: String,
    // История строк, которые мы показываем в нижней панели логов.
    pub(crate) log_lines: Vec<String>,
    // Внутренний флаг завершения приложения.
    should_quit: bool,
    // Следующий ID для новой сессии.
    next_id: usize,
    // Находимся ли мы сейчас в режиме ввода типа устройства.
    add_mode: bool,
    // Находимся ли мы сейчас в режиме переименования выбранного устройства.
    rename_mode: bool,
    // Режим инъекции callback-адреса: игрок вводит hex-адрес (например, адрес system),
    // который будет записан прямо в header->log_callback pinned-устройства.
    write_callback_mode: bool,
    // Накопленный hex-ввод для W-режима (поддерживает "0x..." и просто hex-цифры).
    pub(crate) callback_hex_input: String,
    // Текущий угол луча радара на карте.
    pub radar_angle: f64,
}

impl App {
    // Конструктор: создаёт App в начальном состоянии.
    /// Назначение: создать начальное состояние приложения без устройств и без активного ввода.
    pub fn new() -> Self {
        // Создаём состояние списка по умолчанию.
        let mut list_state = ListState::default();
        // В начале ничего не выбрано.
        list_state.select(None);

        Self {
            // Пока устройств нет.
            active_devices: Vec::new(),
            // Сохраняем созданное состояние списка.
            list_state,
            // Ничего не pinned.
            pinned_device: None,
            // Поле ввода типа устройства пустое.
            device_type_input: String::new(),
            // Поле ввода нового имени тоже пустое.
            rename_input: String::new(),
            // Hex-ввод для W-режима тоже начинаем пустым.
            callback_hex_input: String::new(),
            // Журнал логов начинаем с подсказки, чтобы нижняя панель не была пустой.
            log_lines: vec![
                "log stream armed; press L/l on a selected node or pinned ghost.".to_owned(),
            ],
            // Выход не запрошен.
            should_quit: false,
            // Первый ID будет 1.
            next_id: 1,
            // Add mode выключен.
            add_mode: false,
            // Rename mode тоже выключен.
            rename_mode: false,
            // W-режим инъекции callback выключен.
            write_callback_mode: false,
            // Радар стартует с угла 0 радиан.
            radar_angle: 0.0,
        }
    }

    // Геттер: внешняя логика спрашивает, нужно ли завершить приложение.
    /// Назначение: сообщить внешнему циклу, нужно ли завершать приложение.
    pub(crate) fn should_quit(&self) -> bool {
        self.should_quit
    }

    // Сеттер: помечаем приложение на завершение.
    /// Назначение: пометить приложение на завершение.
    pub(crate) fn quit(&mut self) {
        self.should_quit = true;
    }

    // Маленький helper для нижней панели логов.
    /// Назначение: добавить строку в журнал событий и не дать ему бесконечно разрастаться.
    fn push_log_line(&mut self, message: impl Into<String>) {
        // Кладём новую строку в конец, чтобы внизу всегда были самые свежие события.
        self.log_lines.push(message.into());
        // Ограничиваем размер журнала, чтобы приложение не копило строки бесконечно.
        const MAX_LOG_LINES: usize = 128;
        // Если строк накопилось слишком много, удаляем самые старые из начала буфера.
        if self.log_lines.len() > MAX_LOG_LINES {
            // overflow = сколько строк нужно выкинуть, чтобы вернуться к лимиту.
            let overflow = self.log_lines.len() - MAX_LOG_LINES;
            // drain(0..overflow) удаляет старые записи из начала вектора.
            self.log_lines.drain(0..overflow);
        }
    }

    // Для PWN-флоу важнее всего dangling pinned-сессия.
    /// Назначение: выбрать главную цель для действий пользователя: dangling pinned ghost, иначе выбранную ноду, иначе просто pinned.
    fn preferred_interaction_target(&self) -> Option<DeviceEntry> {
        // Если pinned-устройство уже freed, именно оно должно быть целью R и L/l.
        if let Some(pinned) = self.pinned_device.as_ref() {
            if !self.pinned_is_active() {
                return Some(pinned.clone());
            }
        }
        // Иначе сначала пробуем выбранную активную ноду, а если её нет - обычный pinned fallback.
        self.selected_device()
            .cloned()
            .or_else(|| self.pinned_device.clone())
    }

    // Проверяем, совпадает ли ptr с dangling pinned-устройством.
    /// Назначение: быстро понять, указывает ли данный ptr на уже освобождённый pinned-объект.
    fn is_dangling_pinned_ptr(&self, ptr: *mut c_void) -> bool {
        self.pinned_device
            .as_ref()
            .is_some_and(|pinned| pinned.ptr == ptr && !self.pinned_is_active())
    }

    // Узнаём extra_data-адрес из C-session.
    /// Назначение: достать указатель на extra_data-чанк из C-session, чтобы читать его в телеметрии.
    fn session_heap_ptr(ptr_to_session: *mut c_void) -> *mut c_void {
        // NULL-сессию не разыменовываем.
        if ptr_to_session.is_null() {
            return ptr::null_mut();
        }
        // Читаем поле extra_data по C-layout.
        unsafe { (*(ptr_to_session as *mut CtosSession)).extra_data }
    }

    // Узнаём адрес header из C-session.
    /// Назначение: достать указатель на CtosHeader из живой C-session, чтобы логировать его при создании.
    fn session_header_ptr(ptr_to_session: *mut c_void) -> *mut c_void {
        // NULL-сессию не разыменовываем.
        if ptr_to_session.is_null() {
            return ptr::null_mut();
        }
        // Читаем поле header по C-layout.
        unsafe { (*(ptr_to_session as *mut CtosSession)).header as *mut c_void }
    }

    // Пишем новое имя прямо в буфер node_name внутри C-session.
    /// Назначение: создать UAF-write primitive по session pointer и обновить node_name даже после free.
    fn overwrite_session_name(ptr_to_session: *mut c_void, new_name: &str) {
        // Если указатель пустой, писать некуда.
        if ptr_to_session.is_null() {
            return;
        }
        // Переводим void* в layout CtosSession.
        let session = ptr_to_session as *mut CtosSession;
        // name_buf_len = размер буфера node_name в C.
        let name_buf_len = 32_usize;
        // Берём байты нового имени как есть.
        let raw_bytes = new_name.as_bytes();
        // Оставляем место под завершающий '\0'.
        let copy_len = raw_bytes.len().min(name_buf_len - 1);

        unsafe {
            // Получаем адрес начала node_name как обычный байтовый указатель.
            let name_ptr = (*session).node_name.as_mut_ptr() as *mut u8;
            // Сначала зануляем весь 32-байтовый буфер.
            ptr::write_bytes(name_ptr, 0, name_buf_len);
            // Потом копируем в него новое имя.
            ptr::copy_nonoverlapping(raw_bytes.as_ptr(), name_ptr, copy_len);
        }
    }

    // Синхронизируем человекочитаемое имя в Rust-копиях записи.
    /// Назначение: обновить display-name во всех Rust-структурах, которые смотрят на один и тот же session ptr.
    fn sync_name_copies(&mut self, ptr_to_session: *mut c_void, new_name: &str) {
        // Если живая запись всё ещё есть в active_devices, обновляем и её.
        if let Some(device) = self
            .active_devices
            .iter_mut()
            .find(|device| device.ptr == ptr_to_session)
        {
            device.name = new_name.to_owned();
        }

        // Если ptr совпадает с pinned-устройством, обновляем и pinned-копию.
        if let Some(pinned) = self.pinned_device.as_mut() {
            if pinned.ptr == ptr_to_session {
                pinned.name = new_name.to_owned();
            }
        }
    }

    // Проверяем, ждём ли сейчас ввод типа устройства после нажатия A.
    /// Назначение: проверить, ждём ли мы сейчас ввод номера типа устройства.
    pub(crate) fn awaiting_device_type(&self) -> bool {
        self.add_mode
    }

    // Включаем режим добавления.
    /// Назначение: включить режим добавления нового устройства и очистить старый ввод.
    pub(crate) fn start_add_mode(&mut self) {
        // Включаем режим добавления.
        self.add_mode = true;
        // Режимы Add и Rename взаимоисключающие, поэтому выключаем Rename Mode.
        self.rename_mode = false;
        // Стираем ввод имени, если пользователь до этого был в rename-режиме.
        self.rename_input.clear();
        // Очищаем старый ввод номера типа, чтобы не смешивать попытки.
        self.device_type_input.clear();
        // Сразу пишем понятную строку в журнал, чтобы пользователь видел, что режим реально включился.
        self.push_log_line("[mode] add mode armed; enter device type 1..18".to_owned());
    }

    // Выходим из режима добавления.
    /// Назначение: выйти из режима добавления и забыть текущий ввод пользователя.
    pub(crate) fn cancel_add_mode(&mut self) {
        // Выключаем сам режим.
        self.add_mode = false;
        // И стираем накопленные цифры.
        self.device_type_input.clear();
    }

    // Проверяем, ждём ли сейчас ввод нового имени для выбранного устройства.
    /// Назначение: проверить, включён ли сейчас режим переименования устройства.
    pub(crate) fn awaiting_rename(&self) -> bool {
        self.rename_mode
    }

    // Включаем режим переименования и подставляем текущее имя цели.
    /// Назначение: начать переименование выбранного устройства или dangling pinned ghost и подставить его текущее имя в поле ввода.
    pub(crate) fn start_rename_mode(&mut self) {
        // Берём приоритетную цель для rename: ghost после free важнее обычного selected.
        let Some(target) = self.preferred_interaction_target() else {
            // Если нет ни selected, ни pinned, логируем отсутствие цели.
            self.push_log_line("[rename] no selected or pinned device".to_owned());
            return;
        };
        // Проверяем, не работаем ли мы сейчас именно с freed pinned-сессией.
        let is_ghost = self.is_dangling_pinned_ptr(target.ptr);
        // Копируем текущее имя, чтобы подставить его в input-поле.
        let current_name = target.name.clone();

        // Включаем rename-режим.
        self.rename_mode = true;
        // Выключаем add-режим, потому что одновременно держать оба режима нельзя.
        self.add_mode = false;
        // Стираем возможные цифры от add-mode.
        self.device_type_input.clear();
        // Кладём текущее имя цели в rename-input.
        self.rename_input = current_name.clone();
        // В журнале явно отмечаем, редактируем ли мы живую ноду или dangling ghost.
        if is_ghost {
            self.push_log_line(format!(
                "[mode] rename mode armed for dangling pinned {}",
                current_name
            ));
        } else {
            self.push_log_line(format!("[mode] rename mode armed for {}", current_name));
        }
    }

    // Выходим из режима переименования.
    /// Назначение: выйти из режима переименования и очистить временный ввод имени.
    pub(crate) fn cancel_rename_mode(&mut self) {
        // Выключаем флаг режима.
        self.rename_mode = false;
        // И очищаем временную строку нового имени.
        self.rename_input.clear();
    }

    // Добавляем один символ к новому имени.
    /// Назначение: добавить очередной печатный символ в поле нового имени устройства.
    pub(crate) fn push_rename_char(&mut self, ch: char) {
        // Не даём имени разрастаться бесконечно и пропускаем только печатные символы.
        if !ch.is_control() && self.rename_input.len() < 48 {
            // push(...) добавляет символ в конец строки.
            self.rename_input.push(ch);
        }
    }

    // Удаляем последний символ из нового имени.
    /// Назначение: удалить последний символ из поля нового имени устройства.
    pub(crate) fn backspace_rename_input(&mut self) {
        // pop() удаляет последний символ, если строка не пустая.
        self.rename_input.pop();
    }

    // Пытаемся переименовать текущую цель из строкового ввода.
    /// Назначение: записать новое имя прямо в C-session и синхронизировать Rust-копии даже для dangling pinned ghost.
    pub(crate) fn try_rename_selected_from_input(&mut self) -> bool {
        // Без цели переименовывать нечего.
        let Some(target) = self.preferred_interaction_target() else {
            // Журналируем отсутствие цели для rename.
            self.push_log_line("[rename] no selected or pinned device".to_owned());
            return false;
        };
        // trim() убирает пробелы по краям, чтобы имя из одних пробелов не считалось валидным.
        let new_name = self.rename_input.trim().to_owned();
        // Пустое имя запрещаем.
        if new_name.is_empty() {
            self.push_log_line("[rename] rejected empty name".to_owned());
            return false;
        }

        // Сохраняем исходные данные target до перезаписи.
        let ptr = target.ptr;
        let old_name = target.name.clone();
        let is_ghost = self.is_dangling_pinned_ptr(ptr);

        // Пишем новое имя прямо в node_name внутри C-session.
        Self::overwrite_session_name(ptr, &new_name);
        // И синхронизируем все Rust-копии, которые указывают на тот же session ptr.
        self.sync_name_copies(ptr, &new_name);

        // В журнале явно различаем обычный rename и UAF-write через dangling ghost.
        if is_ghost {
            self.push_log_line(format!(
                "[rename] ghost {} -> {} at session {:p}",
                old_name, new_name, ptr
            ));
        } else {
            self.push_log_line(format!(
                "[rename] {} -> {} at session {:p}",
                old_name, new_name, ptr
            ));
        }
        // После успешного rename закрываем режим ввода.
        self.cancel_rename_mode();
        // Возвращаем true, чтобы event-loop знал об успехе операции.
        true
    }

    // Добавляем одну цифру в поле ввода.
    /// Назначение: добавить очередную цифру в поле ввода типа устройства.
    pub(crate) fn push_device_type_digit(&mut self, ch: char) {
        // Ограничиваем ввод двумя цифрами: у нас диапазон 1..18.
        if self.device_type_input.len() < 2 {
            // push(...) добавляет цифру в конец строки.
            self.device_type_input.push(ch);
        }
    }

    // Имитация Backspace: удаляем последний символ, если он есть.
    /// Назначение: удалить последнюю цифру из поля ввода типа устройства.
    pub(crate) fn backspace_device_type_input(&mut self) {
        // pop() безопасно убирает последний символ, если строка не пустая.
        self.device_type_input.pop();
    }

    // Пытаемся создать устройство из строки, которую ввёл пользователь.
    // Возвращаем true, если удалось, и false, если ввод был некорректным.
    /// Назначение: попытаться создать устройство из текущего строкового ввода пользователя.
    pub(crate) fn try_add_device_from_input(&mut self) -> bool {
        // parse::<u32>() пытается превратить строку вроде "13" в число 13.
        // let Ok(...) = ... else { ... } = удобный способ быстро обработать ошибку.
        let Ok(device_number) = self.device_type_input.parse::<u32>() else {
            // Логируем неверный ввод, чтобы пользователь видел, почему устройство не появилось.
            self.push_log_line(format!(
                "[alloc] invalid device type input: {}",
                self.device_type_input
            ));
            return false;
        };
        // Превращаем число в enum DeviceType.
        let Some(device_type) = DeviceType::from_key(device_number) else {
            // Если такого типа нет, тоже пишем это в журнал.
            self.push_log_line(format!("[alloc] unknown device type: {}", device_number));
            return false;
        };

        // Формируем техническое имя новой сессии.
        let name = format!("{}-{}", device_type.prefix(), self.next_id);
        // Реально создаём устройство.
        self.add_device(&name, device_type);
        // После успешного создания выходим из Add Mode.
        self.cancel_add_mode();
        // Возвращаем true, чтобы вызывающий код знал, что создание прошло успешно.
        true
    }

    // Низкоуровневое создание устройства.
    // Этот метод уже не спрашивает пользователя, а просто делает работу.
    /// Назначение: создать новую C-сессию устройства и добавить её в список активных.
    pub(crate) fn add_device(&mut self, name: &str, d_type: DeviceType) {
        // Переводим Rust-строку в формат C.
        let c_name = CString::new(name).expect("CString conversion failed");
        // unsafe вызов, потому что идём в C.
        // as_ptr() отдаёт указатель на внутренние байты C-строки.
        let ptr = unsafe { ctos_alloc_session(c_name.as_ptr(), d_type.into()) };
        // Защита: если C вернул NULL, просто ничего не добавляем.
        if ptr.is_null() {
            // Журналируем неудачу, чтобы она не выглядела как тихий no-op.
            self.push_log_line(format!("[alloc] {} returned null pointer", name));
            return;
        }
        // Сразу достаём адреса extra_data и header, пока сессия жива.
        let heap_ptr = Self::session_heap_ptr(ptr);
        let header_ptr = Self::session_header_ptr(ptr);

        // Кладём запись в список живых устройств.
        self.active_devices.push(DeviceEntry {
            // Для UI используем текущий next_id как стабильный видимый id.
            id: self.next_id,
            // Сохраняем имя так же, как ввели его в Rust-части.
            name: name.to_owned(),
            // Храним тип, чтобы UI мог показать label и numeric value.
            device_type: d_type,
            // Сохраняем сырой указатель на C-session.
            ptr,
            // И отдельно сохраняем указатель на extra_data-чанк.
            heap_ptr,
            // Сохраняем указатель на header, пока сессия ещё жива.
            // После ctos_free_session session+0 будет содержать tcache fd, а не реальный header.
            // W-примитив использует именно это поле, чтобы писать в log_callback даже для ghost.
            header_ptr,
        });
        // Пишем событие аллокации в журнал.
        // header_ptr здесь важен для полного UAF-пути: после free сессии
        // поле session+0 содержит tcache PROTECT_PTR, а не реальный header.
        // Игрок должен взять HEADER_ADDR именно отсюда, а не читать его из GDB после free.
        self.push_log_line(format!(
            "[alloc] {} ({}) -> session {:p} | header {:p} | heap {:p}",
            name,
            d_type.label(),
            ptr,
            header_ptr,
            heap_ptr
        ));
        // Готовим ID для следующего устройства.
        self.next_id += 1;

        // Если это первое устройство, автоматически выделяем его в списке.
        if self.list_state.selected().is_none() {
            // select(Some(0)) делает первую запись текущей выделенной строкой.
            self.list_state.select(Some(0));
        }
    }

    // Удаляем выбранное устройство из списка живых и освобождаем память в C.
    /// Назначение: удалить выбранное устройство из списка и освободить его C-память.
    pub(crate) fn delete_selected(&mut self) {
        // Если ничего не выбрано, удалять нечего.
        let Some(selected_idx) = self.list_state.selected() else {
            // Логируем отсутствие выделения, чтобы пользователь видел, почему D ничего не делает.
            self.push_log_line("[free] no selected device".to_owned());
            return;
        };
        // Дополнительная защита от выхода индекса за пределы массива.
        if selected_idx >= self.active_devices.len() {
            // Если индекс внезапно устарел, смещаем курсор к последнему валидному элементу.
            self.list_state
                .select(self.active_devices.len().checked_sub(1));
            // И пишем это в журнал.
            self.push_log_line("[free] selected index is out of bounds".to_owned());
            return;
        }

        // remove физически вырезает элемент из Vec и возвращает его нам.
        let device = self.active_devices.remove(selected_idx);
        // Запоминаем, не был ли это одновременно pinned-указатель.
        let freed_pinned = self.is_pinned_ptr(device.ptr);
        // Освобождаем соответствующую C-память.
        unsafe {
            ctos_free_session(device.ptr);
        }
        // После удаления курсор должен смотреть на валидный элемент.
        self.fix_selection_after_remove(selected_idx);
        // Если мы освободили pinned-объект, явно отмечаем появление dangling pointer.
        if freed_pinned {
            // Это полезно именно для PWN-флоу: отдельно показываем session и heap pointers.
            self.push_log_line(format!(
                "[free] {} freed; session {:p} is dangling | heap {:p} now leaks allocator metadata",
                device.name, device.ptr, device.heap_ptr
            ));
        } else {
            // Иначе пишем обычную строку об освобождении.
            self.push_log_line(format!(
                "[free] {} | session {:p} | heap {:p}",
                device.name, device.ptr, device.heap_ptr
            ));
        }
    }

    // Pin не удаляет устройство и не копирует память из C.
    // Он только запоминает запись с тем же ptr, чтобы читать её потом в телеметрии.
    /// Назначение: запомнить выбранное устройство для панели телеметрии.
    pub(crate) fn pin_selected_device(&mut self) {
        // selected_device().cloned() берёт копию выбранной записи, если она существует.
        if let Some(device) = self.selected_device().cloned() {
            // Сначала запоминаем строку журнала, чтобы использовать её после перемещения device.
            let log_line = format!(
                "[pin] {} ({}) | session {:p} | heap {:p}",
                device.name,
                device.device_type.label(),
                device.ptr,
                device.heap_ptr
            );
            // Сохраняем выбранную запись в pinned_device.
            self.pinned_device = Some(device);
            // И отражаем действие в журнале.
            self.push_log_line(log_line);
        } else {
            // Если выбрать было нечего, тоже пишем понятную строку.
            self.push_log_line("[pin] no selected device".to_owned());
        }
    }

    // Возвращаем выбранное устройство, если оно есть.
    /// Назначение: вернуть ссылку на текущее выбранное устройство, если оно есть.
    pub(crate) fn selected_device(&self) -> Option<&DeviceEntry> {
        self.list_state
            .selected()
            .and_then(|index| self.active_devices.get(index))
    }

    // Перемещаем выделение вниз по списку.
    /// Назначение: переместить выделение на следующий элемент списка.
    pub(crate) fn select_next(&mut self) {
        if self.active_devices.is_empty() {
            return;
        }

        // Если не в конце, идём на следующий индекс.
        // Иначе зацикливаемся в начало.
        let next = match self.list_state.selected() {
            Some(index) if index + 1 < self.active_devices.len() => index + 1,
            _ => 0,
        };
        self.list_state.select(Some(next));
    }

    // Перемещаем выделение вверх по списку.
    /// Назначение: переместить выделение на предыдущий элемент списка.
    pub(crate) fn select_previous(&mut self) {
        if self.active_devices.is_empty() {
            return;
        }

        let last = self.active_devices.len() - 1;
        // Если были в начале или ничего не выбрано, прыгаем в конец.
        let next = match self.list_state.selected() {
            Some(0) | None => last,
            Some(index) => index - 1,
        };
        self.list_state.select(Some(next));
    }

    // Проверяем, совпадает ли данный ptr с ptr pinned устройства.
    /// Назначение: проверить, соответствует ли указатель закреплённому устройству.
    pub(crate) fn is_pinned_ptr(&self, ptr: *mut c_void) -> bool {
        self.pinned_device
            .as_ref()
            .is_some_and(|device| device.ptr == ptr)
    }

    // Проверяем, не удалили ли уже pinned устройство из active_devices.
    // Если в active_devices его ptr больше нет, значит pinned pointer стал dangling.
    /// Назначение: понять, жив ли ещё pinned pointer или он уже стал dangling.
    pub(crate) fn pinned_is_active(&self) -> bool {
        self.pinned_device.as_ref().is_some_and(|pinned| {
            self.active_devices
                .iter()
                .any(|device| device.ptr == pinned.ptr)
        })
    }

    /// Назначение: плавно повернуть радарный луч на небольшой угол для следующего кадра.
    pub(crate) fn advance_radar(&mut self) {
        // TAU = полный круг в радианах (примерно 6.28318).
        self.radar_angle = (self.radar_angle + 0.08) % std::f64::consts::TAU;
    }

    // После удаления нужно аккуратно восстановить корректное выделение.
    /// Назначение: восстановить корректное выделение после удаления элемента из списка.
    fn fix_selection_after_remove(&mut self, removed_idx: usize) {
        // Если список стал пустым, снимаем выделение совсем.
        if self.active_devices.is_empty() {
            self.list_state.select(None);
            return;
        }

        // Если удалили последний элемент, переносим курсор на новый последний.
        // Иначе оставляем курсор на том же числовом индексе.
        let next = removed_idx.min(self.active_devices.len() - 1);
        self.list_state.select(Some(next));
    }

    // Перехватываем stdout C-логгера через pipe, чтобы потом показать строки в нижней панели.
    /// Назначение: вызвать C-логгер и вернуть всё, что он напечатал в stdout, одной строкой.
    fn capture_logger_stdout(ptr_to_session: *mut c_void) -> Result<String, String> {
        // В POSIX stdout имеет файловый дескриптор 1.
        const STDOUT_FILENO: i32 = 1;
        // Здесь pipe(...) запишет read-end в [0] и write-end в [1].
        let mut pipe_fds = [0_i32; 2];

        // Весь блок ниже небезопасный, потому что мы работаем с libc и сырыми fd напрямую.
        unsafe {
            // Создаём pipe для перехвата stdout.
            if pipe(pipe_fds.as_mut_ptr()) != 0 {
                // Если pipe создать не удалось, возвращаем понятную ошибку.
                return Err("pipe() failed".to_owned());
            }
            // read_fd понадобится, чтобы потом прочитать всё, что логгер напечатал.
            let read_fd = pipe_fds[0];
            // write_fd станет временным stdout на время вызова ctos_logger(...).
            let write_fd = pipe_fds[1];
            // Сохраняем старый stdout, чтобы восстановить его после вызова.
            let saved_stdout = dup(STDOUT_FILENO);
            // Если сохранить stdout не удалось, закрываем pipe и выходим с ошибкой.
            if saved_stdout < 0 {
                close(read_fd);
                close(write_fd);
                return Err("dup(stdout) failed".to_owned());
            }
            // Подменяем stdout на write-end нашего pipe.
            if dup2(write_fd, STDOUT_FILENO) < 0 {
                close(read_fd);
                close(write_fd);
                close(saved_stdout);
                return Err("dup2(pipe -> stdout) failed".to_owned());
            }
            // Теперь вызываем сам C-логгер: всё его stdout-поведение уйдёт в pipe.
            ctos_logger(ptr_to_session);
            // fflush(NULL) заставляет C stdio немедленно сбросить буфер в pipe.
            fflush(ptr::null_mut());
            // Возвращаем реальный stdout обратно в терминал.
            if dup2(saved_stdout, STDOUT_FILENO) < 0 {
                close(read_fd);
                close(write_fd);
                close(saved_stdout);
                return Err("dup2(restore stdout) failed".to_owned());
            }
            // write-end нам больше не нужен: закрываем его, чтобы read_to_end увидел EOF.
            close(write_fd);
            // Копия старого stdout тоже больше не нужна после успешного восстановления.
            close(saved_stdout);
            // Оборачиваем read_fd в File, чтобы читать его обычными Rust-методами.
            let mut reader = File::from_raw_fd(read_fd);
            // Сюда соберём все байты, которые пришли из pipe.
            let mut output = Vec::new();
            // Читаем всё до конца pipe.
            if reader.read_to_end(&mut output).is_err() {
                // Если чтение сломалось, возвращаем ошибку.
                return Err("read(pipe) failed".to_owned());
            }
            // Превращаем байты в строку, мягко переживая не-UTF8 через from_utf8_lossy(...).
            Ok(String::from_utf8_lossy(&output).trim_end().to_owned())
        }
    }

    /// Назначение: вызвать C-логгер для выбранной ноды или dangling pinned ghost и отправить результат в лог-панель настолько безопасно, насколько это возможно для exploit flow.
    pub(crate) fn trigger_selected_log(&mut self) {
        // Берём приоритетную цель для logger: dangling pinned ghost важнее обычного selected.
        let Some(device) = self.preferred_interaction_target() else {
            // Если не нашли ни selected, ни pinned, пишем это в журнал.
            self.push_log_line("[logger] no selected or pinned device".to_owned());
            return;
        };
        // Проверяем, не вызываем ли мы callback уже на freed pinned-сессии.
        let is_ghost = self.is_dangling_pinned_ptr(device.ptr);

        // Сначала пишем служебную строку о самом факте вызова callback.
        if is_ghost {
            self.push_log_line(format!(
                "[logger] refused dangling pinned callback for {} at session {:p}",
                device.name, device.ptr
            ));
            self.push_log_line(
                "[logger] ghost session was freed: session->header now contains allocator metadata, so calling ctos_logger here would segfault".to_owned(),
            );
            self.push_log_line(
                "[logger] use ghost devices for leak/rename only; trigger L on a live device after rewriting its callback".to_owned(),
            );
            return;
        }

        self.push_log_line(format!(
            "[logger] invoke callback for {} at session {:p}",
            device.name, device.ptr
        ));

        // Для живых объектов можно безопасно использовать helper, который подменяет stdout pipe'ом и собирает результат.
        match Self::capture_logger_stdout(device.ptr) {
            // Если логгер что-то вывел, разбиваем вывод по строкам и добавляем каждую отдельно.
            Ok(output) if !output.is_empty() => {
                // lines() делит текст по '\\n' , чтобы журнал был читаемым даже для многострочного вывода.
                for line in output.lines() {
                    // Каждую строку помечаем префиксом, чтобы её было легко отличить от action-log.
                    self.push_log_line(format!("[stdout] {}", line));
                }
            }
            // Если вызов прошёл, но stdout оказался пустым, тоже явно отражаем это в журнале.
            Ok(_) => self.push_log_line("[stdout] <no output>".to_owned()),
            // Если перехват stdout сломался, пишем техническую ошибку в лог-панель.
            Err(err) => self.push_log_line(format!("[logger] capture failed: {}", err)),
        }
    }

    // ─── W-режим: инъекция произвольного адреса в log_callback ───────────────

    /// Назначение: проверить, ждём ли мы сейчас ввод hex-адреса для записи в log_callback.
    pub(crate) fn awaiting_callback_address(&self) -> bool {
        self.write_callback_mode
    }

    /// Назначение: активировать режим инъекции callback-адреса для pinned-устройства.
    /// Игрок вводит hex (например, адрес system()), который будет записан в header->log_callback.
    pub(crate) fn start_write_callback_mode(&mut self) {
        let Some(pinned) = self.pinned_device.as_ref() else {
            self.push_log_line("[inject] no pinned device — pin a device first".to_owned());
            return;
        };
        let is_ghost = !self.pinned_is_active();
        let state = if is_ghost { "ghost/UAF" } else { "live" };
        let name = pinned.name.clone();
        let header_ptr = pinned.header_ptr;
        // Выключаем все остальные режимы ввода.
        self.add_mode = false;
        self.rename_mode = false;
        self.device_type_input.clear();
        self.rename_input.clear();
        // Включаем W-режим и очищаем поле hex-ввода.
        self.write_callback_mode = true;
        self.callback_hex_input.clear();
        self.push_log_line(format!(
            "[inject] CALLBACK INJECT MODE | target: {} ({}) | header @ {:p} | enter hex address",
            name, state, header_ptr
        ));
    }

    /// Назначение: выйти из W-режима и сбросить hex-ввод.
    pub(crate) fn cancel_write_callback_mode(&mut self) {
        self.write_callback_mode = false;
        self.callback_hex_input.clear();
    }

    /// Назначение: добавить символ к накапливаемому hex-адресу (принимаем 0-9, a-f, A-F, x).
    pub(crate) fn push_callback_hex_char(&mut self, ch: char) {
        // Максимум "0x" + 16 hex-цифр = 18 символов.
        if self.callback_hex_input.len() < 18 && (ch.is_ascii_hexdigit() || ch == 'x') {
            self.callback_hex_input.push(ch);
        }
    }

    /// Назначение: удалить последний символ hex-ввода.
    pub(crate) fn backspace_callback_hex_input(&mut self) {
        self.callback_hex_input.pop();
    }

    /// Назначение: распарсить введённый hex как u64 и записать его в header->log_callback.
    /// Это позволяет перезаписать callback без GDB — ключевой примитив для remote-эксплойта.
    pub(crate) fn try_inject_callback_from_input(&mut self) -> bool {
        let Some(pinned) = self.pinned_device.as_ref() else {
            self.push_log_line("[inject] no pinned device".to_owned());
            return false;
        };

        // Принимаем как "0x7f...abc" так и "7f...abc".
        let raw = self
            .callback_hex_input
            .trim()
            .trim_start_matches("0x")
            .to_owned();
        let Ok(addr) = u64::from_str_radix(&raw, 16) else {
            self.push_log_line(format!(
                "[inject] invalid hex input: '{}'",
                self.callback_hex_input
            ));
            return false;
        };

        let header_ptr = pinned.header_ptr;
        let target_name = pinned.name.clone();
        let is_ghost = !self.pinned_is_active();
        let state = if is_ghost { "ghost/UAF" } else { "live" };

        if header_ptr.is_null() {
            self.push_log_line("[inject] header_ptr is null — cannot write".to_owned());
            return false;
        }

        // log_callback находится по смещению +8 от начала CtosHeader:
        //   device_type (2) + status (2) + padding (4) = 8 байт.
        unsafe {
            let callback_slot = (header_ptr as *mut u8).add(8) as *mut u64;
            *callback_slot = addr;
        }

        self.push_log_line(format!(
            "[inject] WROTE 0x{:016x} -> header {:p} + 0x8 | target: {} ({})",
            addr, header_ptr, target_name, state
        ));
        self.cancel_write_callback_mode();
        true
    }
}
