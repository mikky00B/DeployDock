// Package docker implements engine.ContainerRuntime by shelling out to the
// docker CLI. CLI-backed on purpose (spec §60: avoid unnecessary
// dependencies); the interface keeps it swappable for the Docker SDK later.
package docker

import (
	"context"
	"fmt"
	"os/exec"
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
func (r *Runtime) Run(ctx context.Context, cfg engine.RunConfig) (string, int, error) {
	args := []string{"run", "-d", "--name", cfg.Name, "--restart", "unless-stopped",
		"-p", fmt.Sprintf("127.0.0.1::%d", cfg.Port)}
	for key, value := range cfg.Env {
		args = append(args, "-e", fmt.Sprintf("%s=%s", key, value))
	}
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

func (r *Runtime) StopAndRemove(ctx context.Context, name string) error {
	if _, err := r.run(ctx, "rm", "-f", name); err != nil {
		// Absent containers are fine; anything else surfaces.
		if !strings.Contains(err.Error(), "No such container") {
			return err
		}
	}
	return nil
}

func (r *Runtime) Rename(ctx context.Context, oldName, newName string) error {
	_, err := r.run(ctx, "rename", oldName, newName)
	return err
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
