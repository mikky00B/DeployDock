// Package client is the agent's HTTP client for the FastAPI control plane,
// implementing the agent side of docs/agent-protocol.md.
package client

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"time"
)

// RegisterRequest is the body of POST /api/v1/agents/register.
type RegisterRequest struct {
	Name         string `json:"name,omitempty"`
	AgentVersion string `json:"agent_version,omitempty"`
	OS           string `json:"os,omitempty"`
	Arch         string `json:"arch,omitempty"`
}

// RegisterResponse is returned once, containing the persistent agent token.
type RegisterResponse struct {
	AgentID                  string `json:"agent_id"`
	AgentToken               string `json:"agent_token"`
	HeartbeatIntervalSeconds int    `json:"heartbeat_interval_seconds"`
}

// HeartbeatRequest reports liveness and optional system metrics.
type HeartbeatRequest struct {
	AgentVersion string           `json:"agent_version,omitempty"`
	Metrics      *MetricsSnapshot `json:"metrics,omitempty"`
}

// MetricsSnapshot carries system utilization as floats so absent probes can
// be omitted instead of reported as fake zeros.
type MetricsSnapshot struct {
	CPUPercent    *float64 `json:"cpu_percent,omitempty"`
	MemoryPercent *float64 `json:"memory_percent,omitempty"`
	DiskPercent   *float64 `json:"disk_percent,omitempty"`
}

// HeartbeatResponse echoes back the interval the server wants.
type HeartbeatResponse struct {
	Status                   string    `json:"status"`
	HeartbeatIntervalSeconds int       `json:"heartbeat_interval_seconds"`
	ServerTime               time.Time `json:"server_time"`
}

// Command is a claimed unit of work (deploy or rollback) with a self-contained
// payload. ClaimToken must be echoed back on result submission.
type Command struct {
	ID           string        `json:"id"`
	DeploymentID string        `json:"deployment_id"`
	Kind         string        `json:"kind"`
	Payload      DeployPayload `json:"payload"`
	ClaimToken   string        `json:"claim_token"`
}

// DeployPayload is the self-contained deployment spec (spec §15: the agent
// never queries the control plane for context).
type DeployPayload struct {
	DeploymentID string  `json:"deployment_id"`
	Kind         string  `json:"kind"`
	CommitSHA    string  `json:"commit_sha"`
	App          AppSpec `json:"app"`
}

// AppSpec describes the application to deploy.
type AppSpec struct {
	Name           string  `json:"name"`
	RepositoryURL  string  `json:"repository_url"`
	Branch         string  `json:"branch"`
	AppPath        string  `json:"app_path"`
	Port           int     `json:"port"`
	HealthcheckURL string  `json:"healthcheck_url"`
	ContainerBase  string  `json:"container_base"`
	CPULimit       *string `json:"cpu_limit,omitempty"`
	MemoryLimit    *string `json:"memory_limit,omitempty"`
}

// CommandResult closes out a claimed command.
type CommandResult struct {
	ClaimToken string `json:"claim_token"`
	Succeeded  bool   `json:"succeeded"`
	Error      string `json:"error,omitempty"`
}

// CommandResultRead is the server's acknowledgement.
type CommandResultRead struct {
	CommandID string `json:"command_id"`
	Status    string `json:"status"`
}

// Event is one deployment progress report (spec §25 event vocabulary).
type Event struct {
	DeploymentID string   `json:"deployment_id"`
	Type         string   `json:"type"`
	Stage        string   `json:"stage,omitempty"`
	Stream       string   `json:"stream,omitempty"`
	Line         string   `json:"line,omitempty"`
	Lines        []string `json:"lines,omitempty"`
	StatusCode   int      `json:"status_code,omitempty"`
	CommitSHA    string   `json:"commit_sha,omitempty"`
	DurationSec  int      `json:"duration_seconds,omitempty"`
	Error        string   `json:"error,omitempty"`
}

// EventBatchRead reports how many events the control plane applied.
type EventBatchRead struct {
	Accepted int `json:"accepted"`
}

// Client talks to one control plane over outbound HTTPS (or HTTP in dev).
type Client struct {
	BaseURL string
	HTTP    *http.Client
}

func New(baseURL string) *Client {
	return &Client{
		BaseURL: baseURL,
		HTTP:    &http.Client{Timeout: 15 * time.Second},
	}
}

// Ping checks control-plane reachability via GET /health.
func (c *Client) Ping(ctx context.Context) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.BaseURL+"/health", nil)
	if err != nil {
		return err
	}
	resp, err := c.HTTP.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("health check returned %s", resp.Status)
	}
	return nil
}

// Register exchanges a single-use registration token for the agent token.
func (c *Client) Register(ctx context.Context, registrationToken string, payload RegisterRequest) (*RegisterResponse, error) {
	var out RegisterResponse
	if err := c.call(ctx, http.MethodPost, "/api/v1/agents/register", registrationToken, payload, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// Heartbeat sends one liveness + metrics report for the given agent.
func (c *Client) Heartbeat(ctx context.Context, agentID, agentToken string, payload HeartbeatRequest) (*HeartbeatResponse, error) {
	var out HeartbeatResponse
	path := fmt.Sprintf("/api/v1/agents/%s/heartbeat", agentID)
	if err := c.call(ctx, http.MethodPost, path, agentToken, payload, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// ClaimCommand claims the agent's oldest queued command; ok is false when the
// queue is empty.
func (c *Client) ClaimCommand(ctx context.Context, agentID, agentToken string) (*Command, bool, error) {
	path := fmt.Sprintf("/api/v1/agents/%s/commands", agentID)
	var out []Command
	if err := c.call(ctx, http.MethodGet, path, agentToken, nil, &out); err != nil {
		return nil, false, err
	}
	if len(out) == 0 {
		return nil, false, nil
	}
	return &out[0], true, nil
}

// PostCommandResult closes out a claimed command.
func (c *Client) PostCommandResult(ctx context.Context, agentID, agentToken, commandID string, result CommandResult) error {
	path := fmt.Sprintf("/api/v1/agents/%s/commands/%s/result", agentID, commandID)
	var out CommandResultRead
	return c.call(ctx, http.MethodPost, path, agentToken, result, &out)
}

// PostEvents submits a batch of deployment events; failures are non-fatal for
// the caller (events are progress reporting, not control flow).
func (c *Client) PostEvents(ctx context.Context, agentID, agentToken string, events []Event) error {
	path := fmt.Sprintf("/api/v1/agents/%s/events", agentID)
	var out EventBatchRead
	return c.call(ctx, http.MethodPost, path, agentToken, map[string]any{"events": events}, &out)
}

// call performs one authenticated JSON request and decodes the response.
func (c *Client) call(ctx context.Context, method, path, token string, payload any, out any) error {
	body, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("could not encode request: %w", err)
	}
	req, err := http.NewRequestWithContext(ctx, method, c.BaseURL+path, bytes.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}

	resp, err := c.HTTP.Do(req)
	if err != nil {
		return fmt.Errorf("could not reach control plane: %w", err)
	}
	defer resp.Body.Close()

	switch {
	case resp.StatusCode >= 200 && resp.StatusCode < 300:
		if out == nil {
			return nil
		}
		if err := json.NewDecoder(resp.Body).Decode(out); err != nil {
			return fmt.Errorf("could not decode response: %w", err)
		}
		return nil
	case resp.StatusCode == http.StatusUnauthorized:
		return fmt.Errorf("control plane rejected the token (401): it may be expired, used, or revoked")
	case resp.StatusCode == http.StatusConflict:
		return fmt.Errorf("agent has been revoked at the control plane (409): re-register to continue")
	default:
		return fmt.Errorf("control plane returned %s", resp.Status)
	}
}
