package config

import (
	"errors"
	"os"
	"path/filepath"
	"testing"
)

func TestSaveAndLoadRoundTrip(t *testing.T) {
	path := filepath.Join(t.TempDir(), "deploydock", "agent.json")
	t.Setenv("DEPLOYDOCK_AGENT_CONFIG", path)

	state := &State{
		ControlPlaneURL:          "http://127.0.0.1:8000",
		AgentID:                  "agent-1",
		AgentToken:               "dck_at_secret",
		HeartbeatIntervalSeconds: 30,
	}
	if err := Save(state); err != nil {
		t.Fatalf("Save failed: %v", err)
	}

	info, err := os.Stat(path)
	if err != nil {
		t.Fatalf("state file missing: %v", err)
	}
	// On POSIX the file must be owner-only because it holds the token.
	if info.Mode().Perm() != 0o600 && os.Getenv("GOOS") == "" && info.Mode().Perm()&0o077 != 0 {
		t.Errorf("state file permissions too open: %v", info.Mode().Perm())
	}

	loaded, err := Load()
	if err != nil {
		t.Fatalf("Load failed: %v", err)
	}
	if *loaded != *state {
		t.Errorf("loaded = %+v, want %+v", loaded, state)
	}
}

func TestLoadWithoutStateFileReturnsNotRegistered(t *testing.T) {
	t.Setenv("DEPLOYDOCK_AGENT_CONFIG", filepath.Join(t.TempDir(), "missing.json"))

	if _, err := Load(); !errors.Is(err, ErrNotRegistered) {
		t.Errorf("err = %v, want ErrNotRegistered", err)
	}
}

func TestLoadRejectsIncompleteState(t *testing.T) {
	path := filepath.Join(t.TempDir(), "agent.json")
	t.Setenv("DEPLOYDOCK_AGENT_CONFIG", path)
	// Token missing: the file exists but is not a usable registration.
	if err := os.WriteFile(path, []byte(`{"control_plane_url":"http://x"}`), 0o600); err != nil {
		t.Fatal(err)
	}

	if _, err := Load(); !errors.Is(err, ErrNotRegistered) {
		t.Errorf("err = %v, want ErrNotRegistered", err)
	}
}
