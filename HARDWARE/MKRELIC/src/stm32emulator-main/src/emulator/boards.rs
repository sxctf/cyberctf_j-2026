use std::{env, path::PathBuf};

use crate::challenge::challenges::ChallengeKind;

#[derive(Clone, Debug)]
pub struct BoardView {
    /// RU: Задание, которое сейчас загружено в эмулятор.
    /// EN: Challenge currently loaded into the emulator.
    pub challenge: ChallengeKind,
    /// RU: Человекочитаемый заголовок в верхней части TUI.
    /// EN: Human-readable title shown at the top of the TUI.
    pub title: String,
    /// RU: Краткое описание задачи для пользователя/оператора.
    /// EN: Short task description for the operator.
    pub brief: String,
    /// RU: Последний счетчик инструкций/шагов, который сообщил эмулятор.
    /// EN: Last instruction/step counter reported by the emulator.
    pub step: u64,
    /// RU: Значение счетчика TIM2; полезно для задач с временными окнами.
    /// EN: TIM2 counter value, useful for timing-window challenges.
    pub tim2_cnt: u32,
    /// RU: Снимок регистра входов GPIOA.
    /// EN: GPIOA input data register snapshot.
    pub gpioa_idr: u16,
    /// RU: Снимок регистра выходов GPIOA.
    /// EN: GPIOA output data register snapshot.
    pub gpioa_odr: u16,
    /// RU: Производный флаг service mode для логики задания и индикаторов UI.
    /// EN: Derived service-mode flag for challenge logic and UI indicators.
    pub service_mode: bool,
    /// RU: Производный уровень входного пина PA0.
    /// EN: Derived PA0 input level.
    pub pa0_high: bool,
    /// RU: Производное состояние LED на PA5 из 5-го бита GPIOA ODR.
    /// EN: Derived PA5 LED state from GPIOA ODR bit 5.
    pub pa5_led_on: bool,
    /// RU: Базовый адрес последней просматриваемой/дампленной области памяти.
    /// EN: Base address of the last watched/dumped memory region.
    pub watch_addr: u32,
    /// RU: Длина последней просматриваемой/дампленной области памяти.
    /// EN: Length of the last watched/dumped memory region.
    pub watch_len: usize,
    /// RU: Специфичный для задания обратный счетчик активного временного окна.
    /// EN: Challenge-specific countdown for an armed timing window.
    pub armed_ticks_left: u32,
    /// RU: Открыто ли сейчас окно fault/glitch, если оно есть в задании.
    /// EN: Whether the challenge-specific fault/glitch window is currently open.
    pub fault_window_open: bool,
    /// RU: Видит ли UI признаки того, что manifest задания присутствует.
    /// EN: Whether the UI has evidence that the challenge manifest is present.
    pub manifest_present: bool,
    /// RU: Специфичное для задания latch/debug значение, вынесенное для обучения.
    /// EN: Challenge-specific latch/debug value surfaced for learning.
    pub service_latch: u32,
    /// RU: Заблокировано ли еще симулированное окно с флагом.
    /// EN: Whether the simulated flag window is still locked.
    pub flag_window_locked: bool,
    /// RU: Есть ли признаки, что flag-like blob существует во flash.
    /// EN: Whether a flag-like blob is believed to exist in flash.
    pub flash_flag_blob_present: bool,
    /// RU: Последний UART-текст, отправленный пользователем/TUI в плату.
    /// EN: Last UART text sent from the user/TUI into the board.
    pub last_uart_rx: Option<String>,
    /// RU: Последний UART-текст, который firmware платы отправила наружу.
    /// EN: Last UART text emitted by firmware from the board.
    pub last_uart_tx: Option<String>,
    /// RU: Однострочный статус от bridge/runtime.
    /// EN: One-line status from the bridge/runtime.
    pub status_line: String,
    /// RU: Отфильтрованный UART-only лог для serial-панели.
    /// EN: Filtered UART-only log for the serial panel.
    pub uart_log: Vec<String>,
    /// RU: Отфильтрованный лог эмулятора/bridge для диагностики.
    /// EN: Filtered emulator/bridge log for diagnostics.
    pub emulator_log: Vec<String>,
    /// RU: Человекочитаемый дамп памяти для текущей наблюдаемой области.
    /// EN: Human-readable memory dump for the current watched region.
    pub watch_dump: String,
    /// RU: Команды, отправленные через UI в текущей сессии.
    /// EN: Commands issued through the UI in this session.
    pub command_log: Vec<String>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum BoardProfile {
    ProjectLab,
    Saturn,
}

impl BoardProfile {
    /// RU: Возвращает профили в порядке предпочтения запуска.
    /// EN: Returns profiles in launch preference order.
    ///
    /// RU: Лабораторный профиль проекта приоритетнее; vendored-профиль нужен как
    /// RU: детерминированный fallback на машинах только с upstream-ассетами.
    /// EN: The project-owned lab profile wins when it exists; the vendored profile
    /// EN: is a deterministic fallback for machines that only have upstream assets.
    pub fn all() -> [Self; 2] {
        [Self::ProjectLab, Self::Saturn]
    }

    /// RU: Находит корневой каталог файлов для профиля платы.
    /// EN: Resolves the filesystem root for this board profile.
    ///
    /// RU: Код запуска использует его как рабочую директорию child process, чтобы
    /// RU: относительные ассеты профиля находились так же, как в upstream.
    /// EN: Launch code uses this as the child process working directory so relative
    /// EN: assets in the profile keep resolving the same way as in upstream.
    pub fn root(self) -> PathBuf {
        match self {
            Self::ProjectLab => PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                .join("profiles")
                .join("stm32_lab"),
            Self::Saturn => vendored_repo_root().join("saturn"),
        }
    }

    /// RU: Возвращает YAML-конфиг, который передается бинарнику эмулятора.
    /// EN: Returns the YAML config file passed to the emulator binary.
    ///
    /// RU: Bridge-протоколу нужен запуск конкретной конфигурации платы, а не просто
    /// RU: generic executable.
    /// EN: The bridge protocol expects the child process to boot a concrete board
    /// EN: configuration, not just a generic executable.
    pub fn config_path(self) -> PathBuf {
        self.root().join("config.yaml")
    }

    /// RU: Объясняет источник профиля для status text и диагностики.
    /// EN: Explains where the profile came from for status text and diagnostics.
    ///
    /// RU: Это контекст для оператора: он помогает отличить наш lab profile от
    /// RU: vendored upstream fallback.
    /// EN: This is operator-facing context; it helps distinguish "using our lab
    /// EN: profile" from "using vendored upstream fallback".
    pub fn description(self) -> &'static str {
        match self {
            Self::ProjectLab => "project-owned prebuilt stm32-emulator profile",
            Self::Saturn => "vendored prebuilt stm32-emulator profile `saturn`",
        }
    }
}

/// RU: Находит корень checked-in upstream-репозитория эмулятора.
/// EN: Resolves the checked-in upstream emulator repository root.
///
/// RU: Путь строится от `CARGO_MANIFEST_DIR`, поэтому он стабилен независимо от
/// RU: текущей директории shell.
/// EN: The path is based on `CARGO_MANIFEST_DIR`, so it stays stable regardless of
/// EN: the user's current shell directory.
pub fn vendored_repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("vendor")
        .join("stm32-emulator")
        .join("stm32-emulator-main")
}

/// RU: Преобразует enum задания в короткий slug для логов и status text.
/// EN: Maps a challenge enum to the compact slug used in logs and status text.
///
/// RU: Slug намеренно стабильный и lowercase: его проще grep-ать, и он реже
/// RU: меняется, чем UI-заголовки.
/// EN: The slug is intentionally stable and lowercase because it is easier to grep
/// EN: and less likely to change than UI titles.
pub fn challenge_slug(challenge: ChallengeKind) -> &'static str {
    match challenge {
        ChallengeKind::SramRecovery => "sram",
        ChallengeKind::GlitchUnlock => "glitch",
    }
}
