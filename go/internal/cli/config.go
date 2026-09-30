// Package cli implements the deploydock developer CLI (spec §28-32).
//
// The CLI talks to the FastAPI control plane only — it never SSHes into VPS
// infrastructure (spec §4.2) and never touches PostgreSQL directly (§28).
package cli

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// Config is the persisted CLI state (spec §31).
type Config struct {
	APIURL string `json:"-"`
	Token  string `json:"-"`
}

// ConfigPath resolves the config file location.
func ConfigPath() (string, error) {
	if override := os.Getenv("DEPLOYDOCK_CONFIG"); override != "" {
		return override, nil
	}
	base, err := os.UserConfigDir()
	if err != nil {
		return "", fmt.Errorf("could not resolve config directory: %w", err)
	}
	return filepath.Join(base, "deploydock", "config.yaml"), nil
}

// LoadConfig reads the CLI config; missing file yields an empty config.
func LoadConfig() (*Config, error) {
	path, err := ConfigPath()
	if err != nil {
		return nil, err
	}
	raw, err := os.ReadFile(path) //nolint:gosec // path from env/config dir
	if err != nil {
		if os.IsNotExist(err) {
			return &Config{}, nil
		}
		return nil, fmt.Errorf("could not read %s: %w", path, err)
	}
	config := &Config{}
	for _, line := range strings.Split(string(raw), "\n") {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		key, value, ok := strings.Cut(line, ":")
		if !ok {
			continue
		}
		key, value = strings.TrimSpace(key), strings.TrimSpace(value)
		switch key {
		case "api_url":
			config.APIURL = value
		case "token":
			config.Token = value
		}
	}
	return config, nil
}

// SaveConfig writes the config as simple YAML (spec §31 names config.yaml).
func SaveConfig(config *Config) error {
	path, err := ConfigPath()
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return fmt.Errorf("could not create config directory: %w", err)
	}
	content := fmt.Sprintf("api_url: %s\ntoken: %s\n", config.APIURL, config.Token)
	if err := os.WriteFile(path, []byte(content), 0o600); err != nil { //nolint:gosec // contains the token
		return fmt.Errorf("could not write %s: %w", path, err)
	}
	return nil
}

// ProjectConfig is the deploydock.yaml found in a project directory (§32).
type ProjectConfig struct {
	Name   string
	Port   int
	Health string
}

// LoadProjectConfig reads ./deploydock.yaml (or a --file override).
func LoadProjectConfig(path string) (*ProjectConfig, error) {
	raw, err := os.ReadFile(path) //nolint:gosec // user-specified project file
	if err != nil {
		return nil, fmt.Errorf("could not read %s: %w", path, err)
	}
	project := &ProjectConfig{}
	for _, line := range strings.Split(string(raw), "\n") {
		key, value, ok := strings.Cut(line, ":")
		if !ok {
			continue
		}
		key, value = strings.TrimSpace(key), strings.TrimSpace(value)
		switch key {
		case "name":
			project.Name = strings.Trim(value, `"'`)
		case "port":
			fmt.Sscanf(value, "%d", &project.Port)
		case "path":
			project.Health = strings.Trim(value, `"'`)
		}
	}
	if project.Name == "" {
		return nil, fmt.Errorf("%s is missing a 'name:' entry", path)
	}
	return project, nil
}
