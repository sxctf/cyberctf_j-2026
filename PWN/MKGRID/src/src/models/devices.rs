use std::os::raw::c_void;

// Этот derive просит компилятор автоматически сгенерировать полезные вещи:
// - Clone / Copy: тип можно дешево копировать, потому что enum маленький
// - Debug: можно печатать значение при отладке через {:?}
// - Eq / PartialEq: значения можно сравнивать через ==
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
// repr(u16) говорит Rust хранить enum как 16-битное число.
// Это важно для FFI: C-код ожидает именно uint16_t.
#[repr(u16)]
// enum = перечисление вариантов. Устройство может быть ровно одного из этих типов.
pub enum DeviceType {
    // Слева имя варианта, справа конкретное число, которое уйдет в C-код.
    Camera = 1,
    TrafficLight = 2,
    PowerGrid = 3,
    StreetLight = 4,
    ParkingSensor = 5,
    AirQualitySensor = 6,
    WaterMeter = 7,
    TrashBinSensor = 8,
    EVChargingStation = 9,
    BusStopDisplay = 10,
    SurveillanceDrone = 11,
    SmartPole = 12,
    WeatherStation = 13,
    PedestrianButton = 14,
    CrosswalkSensor = 15,
    GasLeakDetector = 16,
    NoiseMonitor = 17,
    PublicWifiHotspot = 18,
}

// impl From<T> for U позволяет написать u16::from(device_type)
// или device_type.into() и получить число для C-функции.
impl From<DeviceType> for u16 {
    /// Назначение: превратить enum типа устройства в число u16 для передачи в C-код.
    fn from(value: DeviceType) -> Self {
        // "as u16" делает явное приведение enum -> число.
        value as u16
    }
}

// impl DeviceType { ... } = методы, которые относятся именно к DeviceType.
impl DeviceType {
    // from_key пытается превратить номер, введенный пользователем, в enum.
    // Option<Self> значит:
    // - Some(вариант), если номер валиден
    // - None, если номер не существует
    /// Назначение: преобразовать номер, введённый пользователем, в конкретный вариант DeviceType.
    pub fn from_key(value: u32) -> Option<Self> {
        match value {
            1 => Some(Self::Camera),
            2 => Some(Self::TrafficLight),
            3 => Some(Self::PowerGrid),
            4 => Some(Self::StreetLight),
            5 => Some(Self::ParkingSensor),
            6 => Some(Self::AirQualitySensor),
            7 => Some(Self::WaterMeter),
            8 => Some(Self::TrashBinSensor),
            9 => Some(Self::EVChargingStation),
            10 => Some(Self::BusStopDisplay),
            11 => Some(Self::SurveillanceDrone),
            12 => Some(Self::SmartPole),
            13 => Some(Self::WeatherStation),
            14 => Some(Self::PedestrianButton),
            15 => Some(Self::CrosswalkSensor),
            16 => Some(Self::GasLeakDetector),
            17 => Some(Self::NoiseMonitor),
            18 => Some(Self::PublicWifiHotspot),
            // Любой другой номер считаем ошибкой.
            _ => None,
        }
    }

    // prefix возвращает короткое "техническое" имя.
    // Оно нужно, чтобы строить строки вроде power_grid-1.
    // &self значит: метод читает значение, но не забирает его себе.
    /// Назначение: вернуть технический префикс для генерации имени сессии.
    pub fn prefix(&self) -> &'static str {
        // *self здесь разыменовывает ссылку и дает само значение enum.
        match *self {
            Self::Camera => "camera",
            Self::TrafficLight => "traffic_light",
            Self::PowerGrid => "power_grid",
            Self::StreetLight => "street_light",
            Self::ParkingSensor => "parking_sensor",
            Self::AirQualitySensor => "air_quality_sensor",
            Self::WaterMeter => "water_meter",
            Self::TrashBinSensor => "trash_bin_sensor",
            Self::EVChargingStation => "ev_charging_station",
            Self::BusStopDisplay => "bus_stop_display",
            Self::SurveillanceDrone => "surveillance_drone",
            Self::SmartPole => "smart_pole",
            Self::WeatherStation => "weather_station",
            Self::PedestrianButton => "pedestrian_button",
            Self::CrosswalkSensor => "crosswalk_sensor",
            Self::GasLeakDetector => "gas_leak_detector",
            Self::NoiseMonitor => "noise_monitor",
            Self::PublicWifiHotspot => "public_wifi_hotspot",
        }
    }

    // label возвращает красивое имя для UI.
    // Логика та же, но строка уже рассчитана на человека, а не на внутренний идентификатор.
    /// Назначение: вернуть красивое имя типа устройства для отображения в UI.
    pub fn label(&self) -> &'static str {
        match *self {
            Self::Camera => "Camera",
            Self::TrafficLight => "Traffic Light",
            Self::PowerGrid => "Power Grid",
            Self::StreetLight => "Street Light",
            Self::ParkingSensor => "Parking Sensor",
            Self::AirQualitySensor => "Air Quality Sensor",
            Self::WaterMeter => "Water Meter",
            Self::TrashBinSensor => "Trash Bin Sensor",
            Self::EVChargingStation => "EV Charging Station",
            Self::BusStopDisplay => "Bus Stop Display",
            Self::SurveillanceDrone => "Surveillance Drone",
            Self::SmartPole => "Smart Pole",
            Self::WeatherStation => "Weather Station",
            Self::PedestrianButton => "Pedestrian Button",
            Self::CrosswalkSensor => "Crosswalk Sensor",
            Self::GasLeakDetector => "Gas Leak Detector",
            Self::NoiseMonitor => "Noise Monitor",
            Self::PublicWifiHotspot => "Public Wifi Hotspot",
        }
    }
}

// Одна строка в нашем списке устройств.
// Clone нужен, потому что pinned_device хранит копию выбранной записи.
#[derive(Clone, Debug)]
pub struct DeviceEntry {
    // Удобный ID внутри TUI.
    pub id: usize,
    // Имя вида power_grid-1.
    pub name: String,
    // Человеческий тип устройства.
    pub device_type: DeviceType,
    // Сырой указатель на C-session.
    // Через него мы делаем rename и вызываем logger callback.
    pub ptr: *mut c_void,
    // Отдельный указатель на extra_data-чанк.
    // Именно его содержимое удобно читать после free для heap/libc leak.
    pub heap_ptr: *mut c_void,
    // Сырой указатель на CtosHeader, сохранённый при аллокации.
    // После free сессии session+0 содержит tcache PROTECT_PTR, а не реальный header.
    // Этот указатель нужен, чтобы W-примитив мог писать в log_callback даже для ghost-устройств.
    pub header_ptr: *mut c_void,
}
