#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ChallengeKind {
    SramRecovery,
    GlitchUnlock,
}

impl ChallengeKind {
    pub fn from_str(s: &str) -> Option<Self> {
        match s {
            "sram" => Some(Self::SramRecovery),
            "glitch" => Some(Self::GlitchUnlock),
            _ => None,
        }
    }
    pub fn slug(self) -> &'static str {
        match self {
            Self::SramRecovery => "sram",
            Self::GlitchUnlock => "glitch",
        }
    }
}
