// Package agent implements the deploydock-agent commands: registration, the
// heartbeat loop, and self-diagnostics. Deliberately stdlib-only (spec §60).
package agent

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"github.com/deploydock/deploydock/go/internal/client"
	"github.com/deploydock/deploydock/go/internal/config"
	"github.com/deploydock/deploydock/go/internal/system"
)

// Version is overridden at build time via -ldflags "-X ...agent.Version=v2.0.0".
var Version = "dev"

const defaultHeartbeatIntervalSeconds = 30

// commandPollInterval is how often the agent asks for queued work. Deploy
// latency is bounded by this interval; 5s keeps push-to-deploy snappy.
const commandPollInterval = 5 * time.Second

// Register exchanges a control-plane registration token for a persistent
// agent token and stores the resulting state.
func Register(ctx context.Context, controlPlaneURL, registrationToken, name string) (*config.State, error) {
	info := system.ReadInfo()
	if name == "" {
		name = info.Hostname
	}
	api := client.New(controlPlaneURL)
	resp, err := api.Register(ctx, registrationToken, client.RegisterRequest{
		Name:         name,
		AgentVersion: Version,
		OS:           info.OS,
		Arch:         info.Arch,
	})
	if err != nil {
		return nil, err
	}
	state := &config.State{
		ControlPlaneURL:          controlPlaneURL,
		AgentID:                  resp.AgentID,
		AgentToken:               resp.AgentToken,
		HeartbeatIntervalSeconds: resp.HeartbeatIntervalSeconds,
	}
	if err := config.Save(state); err != nil {
		return nil, err
	}
	return state, nil
}

// Run starts the heartbeat loop and the command-polling worker. It blocks
// until the context is cancelled or the control plane revokes the agent
// (409), which is unrecoverable by design.
func Run(ctx context.Context, log *slog.Logger) error {
	state, err := config.Load()
	if err != nil {
		return err
	}
	interval := time.Duration(state.HeartbeatIntervalSeconds) * time.Second
	if interval <= 0 {
		interval = defaultHeartbeatIntervalSeconds * time.Second
	}
	log.Info("agent running", "agent_id", state.AgentID, "control_plane", state.ControlPlaneURL, "interval", interval)

	api := client.New(state.ControlPlaneURL)

	// Command worker: claims and executes deployments serially (one deploy at
	// a time per host; the control plane enforces the same invariant per app).
	commandCtx, stopCommands := context.WithCancel(ctx)
	defer stopCommands()
	go pollCommands(commandCtx, log, api, state)

	ticker := time.NewTicker(interval)
	defer ticker.Stop()

	sendHeartbeat := func() error {
		metrics := system.ReadMetrics()
		resp, err := api.Heartbeat(ctx, state.AgentID, state.AgentToken, client.HeartbeatRequest{
			AgentVersion: Version,
			Metrics: &client.MetricsSnapshot{
				CPUPercent:    metrics.CPUPercent,
				MemoryPercent: metrics.MemoryPercent,
				DiskPercent:   metrics.DiskPercent,
			},
		})
		if err != nil {
			return err
		}
		if resp.HeartbeatIntervalSeconds > 0 && resp.HeartbeatIntervalSeconds != state.HeartbeatIntervalSeconds {
			// The server may change the cadence; honour it immediately.
			state.HeartbeatIntervalSeconds = resp.HeartbeatIntervalSeconds
			interval = time.Duration(resp.HeartbeatIntervalSeconds) * time.Second
			ticker.Reset(interval)
		}
		return nil
	}

	// Heartbeat immediately so the control plane sees the agent right away.
	if err := sendHeartbeat(); err != nil {
		log.Error("initial heartbeat failed", "error", err)
	}

	for {
		select {
		case <-ctx.Done():
			log.Info("agent stopping")
			return nil
		case <-ticker.C:
			if err := sendHeartbeat(); err != nil {
				// Transient failures are logged and retried next tick; the
				// control plane simply derives "offline" until we return.
				log.Warn("heartbeat failed", "error", err)
			}
		}
	}
}

// pollCommands claims and executes commands forever until the context dies.
// Deploy failures do not kill the worker: the result is reported and the next
// poll continues.
func pollCommands(ctx context.Context, log *slog.Logger, api *client.Client, state *config.State) {
	pollInterval := commandPollInterval
	ticker := time.NewTicker(pollInterval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			cmd, ok, err := api.ClaimCommand(ctx, state.AgentID, state.AgentToken)
			if err != nil {
				log.Warn("command poll failed", "error", err)
				continue
			}
			if !ok {
				continue
			}
			log.Info("executing command", "command_id", cmd.ID, "kind", cmd.Kind, "deployment", cmd.Payload.DeploymentID)
			if err := executeCommand(ctx, log, api, state, cmd); err != nil {
				log.Error("command failed", "command_id", cmd.ID, "error", err)
			}
		}
	}
}

// Doctor runs local checks and prints one line per check. It never mutates
// state; exit status is decided by the caller from the returned bool.
func Doctor(ctx context.Context, log *slog.Logger) bool {
	healthy := true

	state, err := config.Load()
	if err != nil {
		log.Error("FAIL state file", "error", err)
		return false
	}
	log.Info("ok state file", "path", "resolved via DEPLOYDOCK_AGENT_CONFIG or user config dir", "agent_id", state.AgentID)

	if state.ControlPlaneURL == "" || state.AgentToken == "" {
		log.Error("FAIL credentials", "detail", "state file is missing the token or control plane URL")
		return false
	}
	log.Info("ok credentials", "control_plane", state.ControlPlaneURL)

	api := client.New(state.ControlPlaneURL)
	if err := api.Ping(ctx); err != nil {
		healthy = false
		log.Error("FAIL control plane reachability", "error", err)
	} else {
		log.Info("ok control plane reachability", "url", state.ControlPlaneURL)
	}

	info := system.ReadInfo()
	log.Info("ok system", "hostname", info.Hostname, "os", info.OS, "arch", info.Arch)
	return healthy
}

// Status prints the locally stored registration summary.
func Status(log *slog.Logger) error {
	state, err := config.Load()
	if err != nil {
		return err
	}
	fmt.Printf("agent id:  %s\n", state.AgentID)
	fmt.Printf("control plane: %s\n", state.ControlPlaneURL)
	fmt.Printf("heartbeat interval: %ds\n", state.HeartbeatIntervalSeconds)
	return nil
}
