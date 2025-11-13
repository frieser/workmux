import os
from pathlib import Path

from .conftest import TmuxEnvironment, poll_until, setup_git_repo


def run_workmux_add(
    env: TmuxEnvironment,
    workmux_exe_path: Path,
    repo_path: Path,
    branch_name: str,
) -> None:
    """
    Helper to run `workmux add` command inside the isolated tmux session.

    Asserts that the command completes successfully.
    """
    stdout_file = env.tmp_path / "workmux_stdout.txt"
    stderr_file = env.tmp_path / "workmux_stderr.txt"
    exit_code_file = env.tmp_path / "workmux_exit_code.txt"

    # Clean up any previous files
    for f in [stdout_file, stderr_file, exit_code_file]:
        if f.exists():
            f.unlink()

    workmux_cmd = (
        f"cd {repo_path} && "
        f"{workmux_exe_path} add {branch_name} "
        f"> {stdout_file} 2> {stderr_file}; "
        f"echo $? > {exit_code_file}"
    )

    env.tmux(["send-keys", "-t", "test:", workmux_cmd, "C-m"])

    # Wait for command to complete
    assert poll_until(exit_code_file.exists, timeout=5.0), (
        "workmux command did not complete in time"
    )

    exit_code = int(exit_code_file.read_text().strip())
    if exit_code != 0:
        stderr = stderr_file.read_text() if stderr_file.exists() else ""
        raise AssertionError(f"workmux add failed with exit code {exit_code}\n{stderr}")


def test_add_creates_worktree(
    isolated_tmux_server: TmuxEnvironment, workmux_exe_path: Path
):
    """Verifies that `workmux add` creates a git worktree."""
    env = isolated_tmux_server
    repo_path = env.tmp_path
    branch_name = "feature-worktree"

    setup_git_repo(repo_path)
    (repo_path / ".workmux.yaml").write_text("panes: []\n")

    run_workmux_add(env, workmux_exe_path, repo_path, branch_name)

    # Verify worktree in git's state
    worktree_list_result = env.run_command(["git", "worktree", "list"])
    assert branch_name in worktree_list_result.stdout

    # Verify worktree directory exists
    expected_worktree_dir = (
        repo_path.parent / f"{repo_path.name}__worktrees" / branch_name
    )
    assert expected_worktree_dir.is_dir()


def test_add_creates_tmux_window(
    isolated_tmux_server: TmuxEnvironment, workmux_exe_path: Path
):
    """Verifies that `workmux add` creates a tmux window with the correct name."""
    env = isolated_tmux_server
    repo_path = env.tmp_path
    branch_name = "feature-window"
    window_name = f"wm-{branch_name}"

    setup_git_repo(repo_path)
    (repo_path / ".workmux.yaml").write_text("panes: []\n")

    run_workmux_add(env, workmux_exe_path, repo_path, branch_name)

    # Verify tmux window was created
    list_windows_result = env.tmux(["list-windows", "-F", "#{window_name}"])
    existing_windows = list_windows_result.stdout.strip().split("\n")
    assert window_name in existing_windows


def test_add_executes_post_create_hooks(
    isolated_tmux_server: TmuxEnvironment, workmux_exe_path: Path
):
    """Verifies that `workmux add` executes post_create hooks in the worktree directory."""
    env = isolated_tmux_server
    repo_path = env.tmp_path
    branch_name = "feature-hooks"
    hook_file = "hook_was_executed.txt"

    setup_git_repo(repo_path)
    config_content = f"""
panes: []
post_create:
  - "touch {hook_file}"
"""
    (repo_path / ".workmux.yaml").write_text(config_content)

    run_workmux_add(env, workmux_exe_path, repo_path, branch_name)

    # Verify hook file was created in the worktree directory
    expected_worktree_dir = (
        repo_path.parent / f"{repo_path.name}__worktrees" / branch_name
    )
    assert (expected_worktree_dir / hook_file).exists()


def test_add_executes_pane_commands(
    isolated_tmux_server: TmuxEnvironment, workmux_exe_path: Path
):
    """Verifies that `workmux add` executes commands in configured panes."""
    env = isolated_tmux_server
    repo_path = env.tmp_path
    branch_name = "feature-panes"
    window_name = f"wm-{branch_name}"
    expected_output = "test pane command output"

    setup_git_repo(repo_path)
    config_content = f"""
panes:
  - command: "echo '{expected_output}'; sleep 0.5"
"""
    (repo_path / ".workmux.yaml").write_text(config_content)

    run_workmux_add(env, workmux_exe_path, repo_path, branch_name)

    # Verify pane command output appears in the pane
    def check_pane_output():
        capture_result = env.tmux(["capture-pane", "-p", "-t", window_name])
        return expected_output in capture_result.stdout

    assert poll_until(check_pane_output, timeout=2.0), (
        f"Expected output '{expected_output}' not found in pane"
    )


def test_add_sources_shell_rc_files(
    isolated_tmux_server: TmuxEnvironment, workmux_exe_path: Path
):
    """Verifies that shell rc files (.zshrc) are sourced and aliases work in pane commands."""
    env = isolated_tmux_server
    repo_path = env.tmp_path
    branch_name = "feature-aliases"
    window_name = f"wm-{branch_name}"
    alias_output = "custom_alias_worked_correctly"

    # Create a custom HOME directory with a .zshrc that defines an alias
    test_home = env.tmp_path / "test_home"
    test_home.mkdir()
    zshrc_content = f"""
# Test alias
alias testcmd='echo "{alias_output}"'
"""
    (test_home / ".zshrc").write_text(zshrc_content)

    setup_git_repo(repo_path)
    config_content = """
panes:
  - command: "testcmd; sleep 0.5"
"""
    (repo_path / ".workmux.yaml").write_text(config_content)

    # Set HOME in the tmux session environment so panes inherit it
    env.tmux(["setenv", "HOME", str(test_home)])

    # Set SHELL to ensure we're using zsh
    shell_path = os.environ.get("SHELL", "/bin/zsh")
    env.tmux(["setenv", "SHELL", shell_path])

    # Now run workmux add normally
    stdout_file = env.tmp_path / "workmux_stdout.txt"
    stderr_file = env.tmp_path / "workmux_stderr.txt"
    exit_code_file = env.tmp_path / "workmux_exit_code.txt"

    # Clean up any previous files
    for f in [stdout_file, stderr_file, exit_code_file]:
        if f.exists():
            f.unlink()

    workmux_cmd = (
        f"cd {repo_path} && "
        f"{workmux_exe_path} add {branch_name} "
        f"> {stdout_file} 2> {stderr_file}; "
        f"echo $? > {exit_code_file}"
    )

    env.tmux(["send-keys", "-t", "test:", workmux_cmd, "C-m"])

    # Wait for command to complete
    assert poll_until(exit_code_file.exists, timeout=5.0), (
        "workmux command did not complete in time"
    )

    exit_code = int(exit_code_file.read_text().strip())
    if exit_code != 0:
        stderr = stderr_file.read_text() if stderr_file.exists() else ""
        raise AssertionError(f"workmux add failed with exit code {exit_code}\n{stderr}")

    # Verify the alias output appears in the pane
    def check_alias_output():
        capture_result = env.tmux(["capture-pane", "-p", "-t", window_name])
        return alias_output in capture_result.stdout

    assert poll_until(check_alias_output, timeout=2.0), (
        f"Alias output '{alias_output}' not found in pane - shell rc file not sourced"
    )
