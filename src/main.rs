mod claude;
mod cli;
mod cmd;
mod config;
mod git;
mod tmux;
mod workflow;

use anyhow::Result;

fn main() -> Result<()> {
    cli::run()
}
