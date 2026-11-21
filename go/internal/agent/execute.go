// Command execution: bridges the control-plane command queue to the
// deployment engine (spec §15 — FastAPI decides, the agent executes).
package agent

import (
	"context"
	"fmt"
	"log/slog"
	"os/exec"
	"time"

	"github.com/deploydock/deploydock/go/internal/caddy"
	"github.com/deploydock/deploydock/go/internal/client"
	"github.com/deploydock/deploydock/go/internal/config"
	"github.com/deploydock/deploydock/go/internal/docker"
	"github.com/deploydock/deploydock/go/internal/engine"
	"github.com/deploydock/deploydock/go/internal/git"
	"github.com/deploydock/deploydock/go/internal/health"
	"github.com/deploydock/deploydock/go/internal/nginx"
	"github.com/deploydock/deploydock/go/internal/stack"
)

// apiEventSink forwards engine events to the control plane. Event posting is
// best-effort: a transient control-plane outage must not abort a deploy that
// is running fine on the VPS.
type apiEventSink struct {
	api          *client.Client
	agentID      string
	agentToken   string
	deploymentID string
	log          *slog.Logger
}

func (s *apiEventSink) Emit(event map[string]any) {
	mapped := client.Event{DeploymentID: s.deploymentID}
	if v, ok := event["type"].(string); ok {
		mapped.Type = v
	}
	if v, ok := event["stage"].(string); ok {
		mapped.Stage = v
	}
	if v, ok := event["stream"].(string); ok {
		mapped.Stream = v
	}
	if v, ok := event["line"].(string); ok {
		mapped.Lines = []string{v}
	}
	if v, ok := event["status_code"].(int); ok {
		mapped.StatusCode = v
	}
	if v, ok := event["commit_sha"].(string); ok {
		mapped.CommitSHA = v
	}
	if v, ok := event["duration_seconds"].(int); ok {
		mapped.DurationSec = v
	}
	if v, ok := event["error"].(string); ok {
		mapped.Error = v
	}
	if err := s.api.PostEvents(context.Background(), s.agentID, s.agentToken, []client.Event{mapped}); err != nil {
		s.log.Warn("could not post deployment event", "type", mapped.Type, "error", err)
	}
}

// executeCommand runs one claimed command through the engine and reports the
// result. The SSH-style free-form commands of v1 are deliberately gone: the
// agent only executes its own staged pipeline (spec §24 — never execute
// arbitrary commands).
//
// Cancellation (audit H2): a watcher polls the control plane while the
// deployment runs; when the user cancels, the per-command context is canceled
// and the engine stops at its next stage boundary — before the proxy switch,
// the point of no return. The result is reported either way so the control
// plane knows execution ended.
func executeCommand(ctx context.Context, log *slog.Logger, api *client.Client, state *config.State, cmd *client.Command) error {
	commandCtx, cancelCommand := context.WithCancel(ctx)
	defer cancelCommand()
	watcherDone := make(chan struct{})
	go func() {
		defer close(watcherDone)
		watchCancellation(commandCtx, cancelCommand, log, api, state, cmd.ID)
	}()

	sink := &apiEventSink{api: api, agentID: state.AgentID, agentToken: state.AgentToken, deploymentID: cmd.Payload.DeploymentID, log: log}

	request := engine.Request{
		DeploymentID: cmd.Payload.DeploymentID,
		Kind:         cmd.Payload.Kind,
		CommitSHA:    cmd.Payload.CommitSHA,
		ImageRef:     cmd.Payload.ImageRef,
		App: engine.AppSpec{
			Name:           cmd.Payload.App.Name,
			RepositoryURL:  cmd.Payload.App.RepositoryURL,
			Branch:         cmd.Payload.App.Branch,
			AppPath:        cmd.Payload.App.AppPath,
			Port:           cmd.Payload.App.Port,
			HealthcheckURL: cmd.Payload.App.HealthcheckURL,
			ContainerBase:  cmd.Payload.App.ContainerBase,
			Env:            cmd.Payload.App.Env,
			Domains:        cmd.Payload.App.Domains,
			CPULimit:       derefString(cmd.Payload.App.CPULimit),
			MemoryLimit:    derefString(cmd.Payload.App.MemoryLimit),
		},
	}

	eng := &engine.Engine{
		Runtime: &docker.Runtime{},
		Git:     &git.Client{},
		Health:  &health.Checker{},
		Proxy:   proxyManagerOrDefault(),
		Stacks:  stack.Provisioner{},
		Sink:    sink,
	}

	err := eng.Execute(commandCtx, request)
	<-watcherDone
	result := client.CommandResult{ClaimToken: cmd.ClaimToken, Succeeded: err == nil}
	if err != nil {
		result.Error = err.Error()
	}
	if postErr := api.PostCommandResult(ctx, state.AgentID, state.AgentToken, cmd.ID, result); postErr != nil {
		log.Error("could not post command result", "command_id", cmd.ID, "error", postErr)
	}
	if err != nil {
		return fmt.Errorf("deployment %s failed: %w", cmd.Payload.DeploymentID, err)
	}
	return nil
}

// cancelPollInterval is how often an executing command asks the control plane
// whether the user canceled it. 3s keeps cancel latency well inside the
// longest stage without meaningful load.
var cancelPollInterval = 3 * time.Second

// watchCancellation polls the command status until cancellation is observed
// or the command context ends, then cancels it (audit H2).
func watchCancellation(ctx context.Context, cancelCommand context.CancelFunc, log *slog.Logger, api *client.Client, state *config.State, commandID string) {
	ticker := time.NewTicker(cancelPollInterval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			status, err := api.GetCommandStatus(ctx, state.AgentID, state.AgentToken, commandID)
			if err != nil {
				// Transient poll failures are not cancellations; retry.
				continue
			}
			if status.CancelRequested {
				log.Info("deployment canceled by user; stopping the pipeline", "command_id", commandID)
				cancelCommand()
				return
			}
		}
	}
}

// proxyManagerOrDefault picks the reverse-proxy manager for this host:
// Caddy when present (automatic TLS), else nginx, else a no-op so apps still
// deploy without a reverse proxy (v3 spec §4.2).
func proxyManagerOrDefault() engine.ProxyManager {
	if _, err := exec.LookPath("caddy"); err == nil {
		return &caddy.Manager{}
	}
	if _, err := exec.LookPath("nginx"); err == nil {
		return &nginx.Manager{}
	}
	return engine.NoopProxy{}
}

func derefString(value *string) string {
	if value == nil {
		return ""
	}
	return *value
}
