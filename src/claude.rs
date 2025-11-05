use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fs;
use std::path::PathBuf;

// Structure of ~/.claude.json - we use a flexible structure to handle unknown fields
#[derive(Debug, Deserialize, Serialize)]
struct ClaudeConfig(HashMap<PathBuf, serde_json::Value>);

/// Get the path to the Claude Code configuration file
fn get_config_path() -> Option<PathBuf> {
    home::home_dir().map(|h| h.join(".claude.json"))
}

/// Prunes entries from ~/.claude.json that point to non-existent directories.
/// Returns the number of entries removed.
pub fn prune_stale_entries() -> Result<usize> {
    let config_path = match get_config_path() {
        Some(path) if path.exists() => path,
        Some(path) => {
            println!("No Claude configuration found at {}", path.display());
            return Ok(0);
        }
        None => {
            println!("Could not determine home directory");
            return Ok(0);
        }
    };

    let contents = fs::read_to_string(&config_path)
        .with_context(|| format!("Failed to read Claude config: {:?}", config_path))?;

    let mut config: ClaudeConfig = serde_json::from_str(&contents)
        .with_context(|| format!("Failed to parse Claude config: {:?}", config_path))?;

    let original_len = config.0.len();
    let mut removed_count = 0;

    config.0.retain(|path, _| {
        // Only consider absolute paths that don't exist
        // We keep relative paths and existing paths
        if path.is_absolute() && !path.exists() {
            println!("  - Removing: {}", path.display());
            removed_count += 1;
            false
        } else {
            true
        }
    });

    if removed_count > 0 {
        // Create a backup
        let backup_path = config_path.with_extension("json.bak");
        fs::copy(&config_path, &backup_path).with_context(|| {
            format!(
                "Failed to create backup of Claude config at {:?}",
                backup_path
            )
        })?;
        println!("\n✓ Created backup at {}", backup_path.display());

        // Write the new file
        let new_contents = serde_json::to_string_pretty(&config.0)?;
        fs::write(&config_path, new_contents).with_context(|| {
            format!("Failed to write updated Claude config to {:?}", config_path)
        })?;

        println!(
            "✓ Removed {} stale {} from {}",
            removed_count,
            if removed_count == 1 {
                "entry"
            } else {
                "entries"
            },
            config_path.display()
        );
    } else {
        println!(
            "No stale entries found in {} ({} total {})",
            config_path.display(),
            original_len,
            if original_len == 1 {
                "entry"
            } else {
                "entries"
            }
        );
    }

    Ok(removed_count)
}
