// Package docker implements engine.ContainerRuntime by shelling out to the
// docker CLI. CLI-backed on purpose (spec §60: avoid unnecessary
// dependencies); the interface keeps it swappable for the Docker SDK later.
package docker

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"sort"
	"strings"

	"github.com/deploydock/deploydock/go/internal/engine"
)

// Runtime is a CLI-backed ContainerRuntime.
type Runtime struct {
	// Bin overrides the docker binary (tests); defaults to "docker".
	Bin string
}

func (r *Runtime) binary() string {
	if r.Bin != "" {
		return r.Bin
	}
	return "docker"
}

func (r *Runtime) run(ctx context.Context, args ...string) (string, error) {
	cmd := exec.CommandContext(ctx, r.binary(), args...)
	var stderr strings.Builder
	cmd.Stderr = &stderr
	out, err := cmd.Output()
	if err != nil {
		return string(out), fmt.Errorf("docker %s: %w: %s",
			strings.Join(args, " "), err, strings.TrimSpace(stderr.String()))
	}
	return string(out), nil
}

// Build builds workspace into imageRef (docker build).
func (r *Runtime) Build(ctx context.Context, workspace, imageRef string) error {
	_, err := r.run(ctx, "build", "-t", imageRef, workspace)
	return err
}

// Run starts a detached container on 127.0.0.1 with a random host port and
// reports the assigned port via `docker port`.
//
// Environment variables are delivered via a 0600 --env-file that is removed
// immediately after the container is created (audit H1): values on the docker
// command line are readable by any local user via ps/proc/cmdline for as
// long as the container runs. Values containing newlines cannot be expressed
// in the env-file format and fall back to -e.
func (r *Runtime) Run(ctx context.Context, cfg engine.RunConfig) (string, int, error) {
	args := []string{"run", "-d", "--name", cfg.Name, "--restart", "unless-stopped",
		"-p", fmt.Sprintf("127.0.0.1::%d", cfg.Port)}
	envFile, inlineArgs, err := r.writeEnvFile(cfg.Env)
	if err != nil {
		return "", 0, fmt.Errorf("write env file: %w", err)
	}
	if envFile != "" {
		defer os.Remove(envFile)
		args = append(args, "--env-file", envFile)
	}
	args = append(args, inlineArgs...)
	if cfg.CPULimit != "" {
		args = append(args, "--cpus", cfg.CPULimit)
	}
	if cfg.MemoryLimit != "" {
		args = append(args, "--memory", cfg.MemoryLimit)
	}
	for key, value := range cfg.Labels {
		args = append(args, "--label", fmt.Sprintf("%s=%s", key, value))
	}
	args = append(args, cfg.Image)

	out, err := r.run(ctx, args...)
	if err != nil {
		return "", 0, err
	}
	containerID := strings.TrimSpace(out)

	portOut, err := r.run(ctx, "port", containerID, fmt.Sprintf("%d/tcp", cfg.Port))
	if err != nil {
		return containerID, 0, fmt.Errorf("resolve published port: %w", err)
	}
	hostPort, err := parseHostPort(portOut)
	if err != nil {
		return containerID, 0, err
	}
	return containerID, hostPort, nil
}

// writeEnvFile serializes environment variables for --env-file and returns
// the inline -e args for values that cannot live in the file format.
func (r *Runtime) writeEnvFile(env map[string]string) (path string, inlineArgs []string, err error) {
	if len(env) == 0 {
		return "", nil, nil
	}
	keys := make([]string, 0, len(env))
	for key := range env {
		keys = append(keys, key)
	}
	sort.Strings(keys)

	var buffer strings.Builder
	for _, key := range keys {
		value := env[key]
		if strings.Contains(value, "\n") || strings.Contains(value, "\r") {
			inlineArgs = append(inlineArgs, "-e", fmt.Sprintf("%s=%s", key, value))
			continue
		}
		fmt.Fprintf(&buffer, "%s=%s\n", key, value)
	}
	if buffer.Len() == 0 {
		return "", inlineArgs, nil
	}
	file, err := os.CreateTemp("", "deploydock-env-*")
	if err != nil {
		return "", nil, err
	}
	if _, err := file.WriteString(buffer.String()); err != nil {
		file.Close()
		os.Remove(file.Name())
		return "", nil, err
	}
	if err := file.Chmod(0o600); err != nil {
		file.Close()
		os.Remove(file.Name())
		return "", nil, err
	}
	if err := file.Close(); err != nil {
		os.Remove(file.Name())
		return "", nil, err
	}
	return file.Name(), inlineArgs, nil
}

// StopAndRemove stops a container with a 30s grace period (so in-flight
// requests can drain before the old release goes away) and removes it,
// ignoring absence.
func (r *Runtime) StopAndRemove(ctx context.Context, name string) error {
	if _, err := r.run(ctx, "stop", "-t", "30", name); err != nil {
		if !strings.Contains(err.Error(), "No such container") {
			return err
		}
		return nil
	}
	if _, err := r.run(ctx, "rm", name); err != nil {
		if !strings.Contains(err.Error(), "No such container") {
			return err
		}
	}
	return nil
}

// PruneDanglingImages removes dangling (untagged intermediate) images, which
// accumulate one layer set per deploy and eventually exhaust the disk
// (audit M11). Tagged release images are kept — retention for those is a
// follow-up.
func (r *Runtime) PruneDanglingImages(ctx context.Context) error {
	_, err := r.run(ctx, "image", "prune", "-f")
	return err
}

func (r *Runtime) Rename(ctx context.Context, oldName, newName string) error {
	_, err := r.run(ctx, "rename", oldName, newName)
	return err
}

// SetAside renames a container out of the way without touching its state;
// renaming a nonexistent container is a no-op (audit H7).
func (r *Runtime) SetAside(ctx context.Context, oldName, newName string) error {
	if _, err := r.run(ctx, "rename", oldName, newName); err != nil {
		if strings.Contains(err.Error(), "No such container") {
			return nil
		}
		return err
	}
	return nil
}

// parseHostPort reads `docker port` output like "8080/tcp -> 127.0.0.1:32771".
func parseHostPort(output string) (int, error) {
	const separator = "127.0.0.1:"
	for _, line := range strings.Split(output, "\n") {
		if index := strings.Index(line, separator); index >= 0 {
			port := strings.TrimSpace(line[index+len(separator):])
			var n int
			if _, err := fmt.Sscanf(port, "%d", &n); err == nil && n > 0 {
				return n, nil
			}
		}
	}
	return 0, fmt.Errorf("could not find 127.0.0.1 host port in docker port output: %q", output)
}
