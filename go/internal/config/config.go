// Package config loads and persists the agent's local state.
//
// The state file holds everything the agent needs to talk to the control
// plane: its identity, bearer token, and heartbeat interval. It is written
// with owner-only permissions because it contains the agent token.
package config

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
)

// State is the persisted identity of a registered agent.
type State struct {
	ControlPlaneURL          string `json:"control_plane_url"`
	AgentID                  string `json:"agent_id"`
	AgentToken               string `json:"agent_token"`
	HeartbeatIntervalSeconds int    `json:"heartbeat_interval_seconds"`
}

// ErrNotRegistered is returned when no valid state file exists yet.
var ErrNotRegistered = errors.New("agent is not registered; run 'deploydock-agent register' first")

// Path returns the state file location, overridable with DEPLOYDOCK_AGENT_CONFIG.
func Path() (string, error) {
	if override := os.Getenv("DEPLOYDOCK_AGENT_CONFIG"); override != "" {
		return override, nil
	}
	base, err := os.UserConfigDir()
	if err != nil {
		return "", fmt.Errorf("could not resolve config directory: %w", err)
	}
	return filepath.Join(base, "deploydock", "agent.json"), nil
}

// Load reads the agent state, returning ErrNotRegistered when absent or empty.
func Load() (*State, error) {
	path, err := Path()
	if err != nil {
		return nil, err
	}
	raw, err := os.ReadFile(path) //nolint:gosec // path comes from env/config dir, not user web input
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return nil, ErrNotRegistered
		}
		return nil, fmt.Errorf("could not read %s: %w", path, err)
	}
	var state State
	if err := json.Unmarshal(raw, &state); err != nil {
		return nil, fmt.Errorf("state file %s is corrupt: %w", path, err)
	}
	if state.AgentToken == "" || state.ControlPlaneURL == "" {
		return nil, ErrNotRegistered
	}
	return &state, nil
}

// Save writes the agent state with owner-only permissions, creating the
// parent directory if needed.
func Save(state *State) error {
	path, err := Path()
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return fmt.Errorf("could not create config directory: %w", err)
	}
	raw, err := json.MarshalIndent(state, "", "  ")
	if err != nil {
		return fmt.Errorf("could not encode state: %w", err)
	}
	if err := os.WriteFile(path, raw, 0o600); err != nil { //nolint:gosec // contains the agent token, hence 0600
		return fmt.Errorf("could not write %s: %w", path, err)
	}
	return nil
}
