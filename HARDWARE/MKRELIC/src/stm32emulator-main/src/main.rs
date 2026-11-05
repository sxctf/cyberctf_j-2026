use anyhow::{Result, anyhow};
use clap::Parser;
use stm32_jeopardy_lab::challenge::challenges::ChallengeKind;
use stm32_jeopardy_lab::emulator::{EmulatorRuntime, run_tui};

#[derive(Parser, Debug)]
#[command(version, about, long_about = None)]
struct Args {
    /// Available sram and glitch mode
    #[arg(short, long)]
    challenge: String,
}

fn main() -> Result<()> {
    let arg = Args::parse();

    let challenge = ChallengeKind::from_str(&arg.challenge).ok_or_else(|| {
        anyhow!(
            "unknown challenge `{}`; expected `sram` or `glitch`",
            arg.challenge
        )
    })?;

    let mut runtime = EmulatorRuntime::new(challenge);

    runtime.connect()?;

    run_tui(&mut runtime)
}
