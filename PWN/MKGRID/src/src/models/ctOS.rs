use std::os::raw::{c_char, c_void};

// Эти repr(C)-структуры повторяют layout из C один в один.
// Это позволяет нам осознанно читать и менять поля по сырым указателям.
#[repr(C)]
pub struct CtosHeader {
    // Тип устройства в C-структуре.
    pub device_type: u16,
    // Статус устройства в C-структуре.
    pub status: u16,
    // Указатель на callback, который потом может быть перехвачен до system(...).
    pub log_callback: *mut c_void,
}

#[repr(C)]
pub struct CtosSession {
    // Указатель на отдельную header-структуру.
    pub header: *mut CtosHeader,
    // Буфер имени прямо внутри session-чанка.
    pub node_name: [c_char; 32],
    // Указатель на extra_data-чанк, который интересен нам для heap leak.
    pub extra_data: *mut c_void,
}
