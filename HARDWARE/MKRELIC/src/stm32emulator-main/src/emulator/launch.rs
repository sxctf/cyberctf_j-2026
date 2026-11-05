use std::{
    env,
    path::{Path, PathBuf},
};

use anyhow::{Result, bail};

use super::{
    boards::{BoardProfile, vendored_repo_root},
    util::split_args,
};

#[derive(Clone, Debug)]
pub struct BridgeLaunch {
    pub command: String,
    pub args: Vec<String>,
    pub workdir: Option<PathBuf>,
    pub description: String,
    pub bridge_protocol: bool,
}

impl BridgeLaunch {
    /// RU: Выбирает, как запускать процесс эмулятора.
    /// EN: Chooses how to start the emulator process.
    ///
    /// RU: Порядок resolution намеренно явный: сначала env override для локального
    /// RU: debug, затем известные prebuilt profiles, затем deterministic
    /// RU: "missing prebuilt" config, который даст понятную ошибку.
    /// EN: Resolution order is intentionally explicit: environment override first
    /// EN: for local debugging, then known prebuilt profiles, then a deterministic
    /// EN: "missing prebuilt" config that produces a clear error.
    pub fn resolve() -> Self {
        if env::var("STM32_EMULATOR_BRIDGE_CMD").is_ok() {
            return Self::from_env();
        }

        for profile in BoardProfile::all() {
            if let Some(launch) = Self::from_prebuilt_profile(profile) {
                return launch;
            }
        }

        Self::missing_prebuilt()
    }

    /// RU: Проверяет, что найденная launch target пригодна до spawn процесса.
    /// EN: Validates that the resolved launch target is usable before spawning it.
    ///
    /// RU: Так мы рано ловим типичные setup-ошибки: нет working directory, нет
    /// RU: executable path или bridge-protocol launch без config argument.
    /// EN: This catches common setup failures early: missing working directory,
    /// EN: missing executable path, or a bridge-protocol launch without a config argument.
    pub fn validate(&self) -> Result<()> {
        if let Some(workdir) = &self.workdir {
            if !workdir.is_dir() {
                bail!("bridge workdir does not exist: {}", workdir.display());
            }
        }

        let command_path = Path::new(&self.command);
        if command_path.components().count() > 1 && !command_path.is_file() {
            bail!(
                "bridge executable does not exist: {}. Provide a prebuilt emulator binary or set STM32_EMULATOR_BRIDGE_CMD",
                command_path.display()
            );
        }

        if self.bridge_protocol && self.args.is_empty() {
            bail!("bridge launch requires a config path argument");
        }

        Ok(())
    }

    /// RU: Собирает launch settings из `STM32_EMULATOR_BRIDGE_*` env variables.
    /// EN: Builds launch settings from `STM32_EMULATOR_BRIDGE_*` environment variables.
    ///
    /// RU: Этот путь нужен для developer override и не предполагает, что custom child
    /// RU: умеет project bridge protocol, если caller сам это не обеспечил.
    /// EN: This path is for developer override and does not assume the custom child
    /// EN: speaks the project bridge protocol unless the caller wraps it that way.
    fn from_env() -> Self {
        Self {
            command: env::var("STM32_EMULATOR_BRIDGE_CMD")
                .unwrap_or_else(|_| "stm32-emulator".to_string()),
            args: split_args(&env::var("STM32_EMULATOR_BRIDGE_ARGS").unwrap_or_default()),
            workdir: env::var("STM32_EMULATOR_BRIDGE_CWD")
                .ok()
                .map(PathBuf::from),
            description: "environment-driven process bridge".to_string(),
            bridge_protocol: false,
        }
    }

    /// RU: Создает bridge-protocol launch для известного prebuilt board profile.
    /// EN: Creates a bridge-protocol launch for a known prebuilt board profile.
    ///
    /// RU: Возвращает `None`, если нет binary или config профиля, чтобы `resolve()`
    /// RU: мог попробовать следующий профиль без hard error.
    /// EN: Returns `None` when either the binary or that profile's config is absent,
    /// EN: so `resolve()` can try the next profile without treating it as a hard error.
    fn from_prebuilt_profile(profile: BoardProfile) -> Option<Self> {
        let binary_path = prebuilt_binary_path(&vendored_repo_root())?;
        let config_path = profile.config_path();

        config_path.is_file().then(|| Self {
            command: binary_path.display().to_string(),
            args: vec![config_path.display().to_string()],
            workdir: Some(profile.root()),
            description: profile.description().to_string(),
            bridge_protocol: true,
        })
    }

    /// RU: Создает launch object, указывающий на ожидаемые vendored binary/config.
    /// EN: Builds a launch object that points at the expected vendored binary/config.
    ///
    /// RU: Объект может не пройти validate; это намеренно, потому что validation
    /// RU: error точно скажет, какого prebuilt artifact или config не хватает.
    /// EN: The object may not validate; that is intentional because the validation
    /// EN: error tells the user exactly which prebuilt artifact or config is missing.
    fn missing_prebuilt() -> Self {
        let repo_root = vendored_repo_root();
        let binary_path = repo_root
            .join("target")
            .join("release")
            .join("stm32-emulator");
        let config_path = BoardProfile::Saturn.config_path();

        Self {
            command: binary_path.display().to_string(),
            args: vec![config_path.display().to_string()],
            workdir: Some(BoardProfile::Saturn.root()),
            description: "deterministic vendored prebuilt stm32-emulator profile".to_string(),
            bridge_protocol: true,
        }
    }
}

/// RU: Ищет release-mode binary vendored-эмулятора.
/// EN: Finds the release-mode vendored emulator binary.
///
/// RU: `Option` позволяет launch resolution отличить "еще не собрано" от проблемы
/// RU: конкретного профиля и продолжить fallback-поиск.
/// EN: Returning `Option` lets launch resolution distinguish "not built yet" from
/// EN: a profile-specific problem and keep trying fallbacks.
fn prebuilt_binary_path(repo_root: &Path) -> Option<PathBuf> {
    let path = repo_root
        .join("target")
        .join("release")
        .join("stm32-emulator");
    path.is_file().then_some(path)
}
