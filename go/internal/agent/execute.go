// Command execution: bridges the control-plane command queue to the
// deployment engine (spec §15 — FastAPI decides, the agent executes).
package agent

import (
	"context"
	"fmt"
	"log/slog"
	"os/exec"

	"github.com/deploydock/deploydock/go/internal/client"
	"github.com/deploydock/deploydock/go/internal/config"
	"github.com/deploydock/deploydock/go/internal/docker"
	"github.com/deploydock/deploydock/go/internal/engine"
	"github.com/deploydock/deploydock/go/internal/git"
	"github.com/deploydock/deploydock/go/internal/health"
	"github.com/deploydock/deploydock/go/internal/nginx"
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
func executeCommand(ctx context.Context, log *slog.Logger, api *client.Client, state *config.State, cmd *client.Command) error {
	sink := &apiEventSink{api: api, agentID: state.AgentID, agentToken: state.AgentToken, deploymentID: cmd.Payload.DeploymentID, log: log}

	request := engine.Request{
		DeploymentID: cmd.Payload.DeploymentID,
		Kind:         cmd.Payload.Kind,
		CommitSHA:    cmd.Payload.CommitSHA,
		App: engine.AppSpec{
			Name:           cmd.Payload.App.Name,
			RepositoryURL:  cmd.Payload.App.RepositoryURL,
			Branch:         cmd.Payload.App.Branch,
			AppPath:        cmd.Payload.App.AppPath,
			Port:           cmd.Payload.App.Port,
			HealthcheckURL: cmd.Payload.App.HealthcheckURL,
			ContainerBase:  cmd.Payload.App.ContainerBase,
			CPULimit:       derefString(cmd.Payload.App.CPULimit),
			MemoryLimit:    derefString(cmd.Payload.App.MemoryLimit),
		},
	}

	eng := &engine.Engine{
		Runtime: &docker.Runtime{},
		Git:     &git.Client{},
		Health:  &health.Checker{},
		Proxy:   proxyManagerOrDefault(),
		Sink:    sink,
	}

	err := eng.Execute(ctx, request)
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

// proxyManagerOrDefault returns a real nginx manager when the nginx binary is
// present, otherwise a no-op so apps still deploy without a reverse proxy.
func proxyManagerOrDefault() engine.ProxyManager {
	if _, err := exec.LookPath("nginx"); err != nil {
		return engine.NoopProxy{}
	}
	return &nginx.Manager{}
}

func derefString(value *string) string {
	if value == nil {
		return ""
	}
	return *value
}
